import re

from sqlalchemy import func
from sqlalchemy.orm import Session
from transformers import pipeline
from langchain_huggingface import HuggingFacePipeline
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import settings
from app.models import CostEmbedding, CostRecord
from app.services.embedding_service import embed_text

# Fully local text-generation model - no API key, no cloud account.
# flan-t5-base is instruction-tuned and small enough to run on CPU comfortably.
_hf_pipeline = pipeline(
    "text2text-generation",
    model=settings.chat_model,
    max_new_tokens=200,
)
_llm = HuggingFacePipeline(pipeline=_hf_pipeline)

# flan-t5-base tends to give short, extractive answers (e.g. just "EC2") regardless of
# instructions asking for more detail. A one-shot example showing the exact answer
# format we want steers it far more reliably than instructions alone.
_prompt = PromptTemplate.from_template(
    "You are CloudPulse AI, an assistant that explains AWS cloud spending. "
    "Answer the question using only the cost data provided. Always include the exact "
    "dollar amount in your answer, not just the service name.\n\n"
    "Example:\n"
    "Cost data:\n"
    "Ranked from highest to lowest total spend, the AWS services are: S3 ($500.00), EC2 ($300.00). "
    "S3 costs the most overall, at $500.00 total.\n"
    "Question: which service costs the most and by how much?\n"
    "Answer: S3 costs the most, at $500.00 total.\n\n"
    "Now answer this question using the data below.\n"
    "Cost data:\n{context}\n\n"
    "Question: {question}\n"
    "Answer:"
)

_chain = _prompt | _llm | StrOutputParser()


def build_cost_documents(db: Session) -> list[str]:
    """Summarize cost data per AWS service into natural-language chunks for embedding.

    Small local models like flan-t5-base are unreliable at comparing numbers across
    several lines of retrieved context, so instead of relying on the LLM to work out
    which service costs the most, we compute the ranking ourselves in Python and hand
    it over as a plain-language fact. The model then only has to relay/rephrase it.
    """
    rows = (
        db.query(
            CostRecord.service,
            func.sum(CostRecord.amount_usd).label("total"),
            func.count(CostRecord.id).label("days"),
        )
        .group_by(CostRecord.service)
        .order_by(func.sum(CostRecord.amount_usd).desc())
        .all()
    )

    docs = [
        f"The AWS service {r.service} cost a total of ${r.total:.2f} over the last {r.days} recorded days, "
        f"averaging ${r.total / r.days:.2f} per day."
        for r in rows
    ]

    if rows:
        ranking = ", ".join(f"{r.service} (${r.total:.2f})" for r in rows)
        docs.append(
            f"Ranked from highest to lowest total spend, the AWS services are: {ranking}. "
            f"{rows[0].service} costs the most overall, at ${rows[0].total:.2f} total."
        )

    return docs


def index_cost_data(db: Session) -> int:
    """Re-embed the current cost summary and store it in pgvector, replacing any prior index."""
    db.query(CostEmbedding).delete()
    docs = build_cost_documents(db)
    for doc in docs:
        db.add(CostEmbedding(content=doc, embedding=embed_text(doc)))
    db.commit()
    return len(docs)


def retrieve_context(db: Session, question: str, k: int = 10) -> list[str]:
    # There are only ~7 documents total (one per service plus the ranking summary),
    # so a generous k effectively means "just pass in everything" - avoids the model
    # missing the one chunk with the actual answer.
    query_vector = embed_text(question)
    results = (
        db.query(CostEmbedding)
        .order_by(CostEmbedding.embedding.cosine_distance(query_vector))
        .limit(k)
        .all()
    )
    return [r.content for r in results]


def _ground_answer(answer: str, context_chunks: list[str]) -> str:
    """
    flan-t5-base often returns a bare entity (e.g. "EC2") instead of a full sentence
    with the dollar figure, no matter how the prompt is worded - it's a known bias
    from its extractive-QA training. Rather than fight the model further, validate
    its answer against the retrieved context and fill in the missing number.
    """
    if "$" in answer:
        return answer

    candidate = answer.strip().rstrip(".")
    if not candidate:
        return answer

    for chunk in context_chunks:
        if candidate.lower() in chunk.lower():
            match = re.search(r"\$[0-9,]+\.\d{2}", chunk)
            if match:
                return f"{candidate} costs ${match.group(0).lstrip('$')} total."

    return answer


def answer_question(db: Session, question: str) -> str:
    context_chunks = retrieve_context(db, question)
    context = "\n".join(context_chunks) if context_chunks else "No cost data indexed yet."
    raw_answer = _chain.invoke({"context": context, "question": question})
    return _ground_answer(raw_answer, context_chunks)
