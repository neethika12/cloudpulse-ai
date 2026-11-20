"""A stand-in for the OpenAI client, so chat and RAG tests need no network or API key.

Embeddings are hashed bag-of-words vectors: texts that share words get similar
vectors, which is enough for retrieval tests to behave sensibly. Chat replies come
from a script, streamed back in chunks shaped like the real SDK's."""
import hashlib
import json
import math
import re
from types import SimpleNamespace

from app.config import settings


def fake_embedding(text: str, dims: int | None = None) -> list[float]:
    dims = dims or settings.embedding_dimensions
    vector = [0.0] * dims
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _chunk(content=None, tool_calls=None, usage=None, empty=False):
    choices = [] if empty else [SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))]
    return SimpleNamespace(choices=choices, usage=usage)


def _tool_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


class FakeOpenAI:
    """script: one entry per streamed chat call, either
         {"content": "final answer"} or {"tool_calls": [("tool_name", {...args})]}.
    rerank: optional function(question, n_passages) -> list of passage numbers.
    judge: optional dict returned for eval-judge calls.
    Once the script runs out, every chat call answers DEFAULT_ANSWER."""

    DEFAULT_ANSWER = {"content": "Default answer."}

    def __init__(self, script=None, rerank=None, judge=None, fail_chat=False):
        self.script = list(script or [])
        self.rerank = rerank
        self.judge = judge
        self.fail_chat = fail_chat
        self.chat_requests: list[dict] = []
        self.embedding_inputs: list[str] = []
        self.embeddings = SimpleNamespace(create=self._embed)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    def _embed(self, model, input, dimensions=None):
        self.embedding_inputs.extend(input)
        data = [SimpleNamespace(index=i, embedding=fake_embedding(t, dimensions)) for i, t in enumerate(input)]
        tokens = sum(len(t.split()) for t in input)
        return SimpleNamespace(data=data, usage=SimpleNamespace(prompt_tokens=tokens))

    def _chat(self, **kwargs):
        if kwargs.get("stream"):
            if self.fail_chat:
                raise ConnectionError("provider down")
            self.chat_requests.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot
            return iter(self._stream(self.script.pop(0) if self.script else self.DEFAULT_ANSWER))
        prompt = kwargs["messages"][-1]["content"]
        if kwargs["messages"][0]["content"].startswith("You grade answers"):
            return self._json_response(self.judge or {"faithfulness": 5, "correctness": 4, "reason": "ok"})
        # Otherwise it is the reranker.
        n = len(re.findall(r"^\[\d+\] ", prompt, flags=re.MULTILINE))
        ranking = self.rerank(prompt, n) if self.rerank else list(range(1, n + 1))
        return self._json_response({"ranking": ranking})

    @staticmethod
    def _json_response(payload):
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                               usage=SimpleNamespace(prompt_tokens=200, completion_tokens=10))

    def _stream(self, step):
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=50)
        if "content" in step:
            text = step["content"]
            middle = len(text) // 2
            yield _chunk(content=text[:middle])
            yield _chunk(content=text[middle:])
        else:
            for i, (name, args) in enumerate(step["tool_calls"]):
                encoded = json.dumps(args)
                yield _chunk(tool_calls=[_tool_delta(i, id=f"call_{i}_{name}", name=name, arguments="")])
                yield _chunk(tool_calls=[_tool_delta(i, arguments=encoded[:3])])
                yield _chunk(tool_calls=[_tool_delta(i, arguments=encoded[3:])])
        yield _chunk(empty=True, usage=usage)
