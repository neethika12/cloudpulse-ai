import { useEffect, useState, FormEvent } from "react";
import {
  Cloud,
  Key,
  Globe,
  Link2,
  RefreshCw,
  Slack,
  AlertCircle,
  CheckCircle2,
  ShieldCheck,
} from "lucide-react";
import { api, CloudAccountInfo } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const AWS_REGIONS = [
  "us-east-1",
  "us-east-2",
  "us-west-1",
  "us-west-2",
  "eu-west-1",
  "eu-central-1",
  "ap-southeast-1",
  "ap-southeast-2",
  "ap-south-1",
];

export default function SettingsPanel() {
  const { user, refreshUser } = useAuth();

  const [account, setAccount] = useState<CloudAccountInfo | null>(null);
  const [loadingAccount, setLoadingAccount] = useState(true);

  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [awsError, setAwsError] = useState<string | null>(null);
  const [awsSuccess, setAwsSuccess] = useState<string | null>(null);

  const [webhookUrl, setWebhookUrl] = useState(user?.slack_webhook_url || "");
  const [savingWebhook, setSavingWebhook] = useState(false);
  const [webhookSaved, setWebhookSaved] = useState(false);

  useEffect(() => {
    api
      .myAccount()
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setLoadingAccount(false));
  }, []);

  useEffect(() => {
    setWebhookUrl(user?.slack_webhook_url || "");
  }, [user?.slack_webhook_url]);

  const handleConnect = async (e: FormEvent) => {
    e.preventDefault();
    setConnecting(true);
    setAwsError(null);
    setAwsSuccess(null);
    try {
      const result = await api.connectAws(accessKeyId, secretAccessKey, region);
      setAccount(result);
      setAwsSuccess(`Connected to AWS account ${result.aws_account_id}.`);
      setAccessKeyId("");
      setSecretAccessKey("");
    } catch (err) {
      setAwsError((err as Error).message);
    } finally {
      setConnecting(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setAwsError(null);
    setAwsSuccess(null);
    try {
      const res = await api.syncAwsCosts();
      setAwsSuccess(`Synced ${res.synced_records} cost records from AWS Cost Explorer.`);
    } catch (err) {
      setAwsError((err as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveWebhook = async (e: FormEvent) => {
    e.preventDefault();
    setSavingWebhook(true);
    setWebhookSaved(false);
    try {
      await api.updateProfile({ slack_webhook_url: webhookUrl || null });
      await refreshUser();
      setWebhookSaved(true);
    } finally {
      setSavingWebhook(false);
    }
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>
            <Cloud size={16} />
            Connect AWS account
          </h2>
        </div>

        {!loadingAccount && account?.is_connected && (
          <div className="status-line" style={{ marginBottom: 16 }}>
            <CheckCircle2 size={13} />
            Connected to AWS account {account.aws_account_id} ({account.aws_region})
          </div>
        )}

        <form onSubmit={handleConnect} className="settings-form">
          <label className="auth-field">
            <Key size={15} />
            <input
              type="text"
              placeholder="AWS Access Key ID"
              value={accessKeyId}
              onChange={(e) => setAccessKeyId(e.target.value)}
              required
            />
          </label>
          <label className="auth-field">
            <Key size={15} />
            <input
              type="password"
              placeholder="AWS Secret Access Key"
              value={secretAccessKey}
              onChange={(e) => setSecretAccessKey(e.target.value)}
              required
            />
          </label>
          <label className="auth-field">
            <Globe size={15} />
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {AWS_REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>

          {awsError && (
            <div className="status-line error">
              <AlertCircle size={13} />
              {awsError}
            </div>
          )}
          {awsSuccess && (
            <div className="status-line">
              <CheckCircle2 size={13} />
              {awsSuccess}
            </div>
          )}

          <div className="card-actions">
            <button type="submit" className="btn" disabled={connecting}>
              <Link2 size={14} />
              {connecting ? "Connecting…" : "Connect account"}
            </button>
            {account?.is_connected && (
              <button
                type="button"
                className="btn secondary"
                onClick={handleSync}
                disabled={syncing}
              >
                <RefreshCw size={14} />
                {syncing ? "Syncing…" : "Sync real cost data"}
              </button>
            )}
          </div>
        </form>

        <div className="settings-note">
          <ShieldCheck size={13} />
          Credentials are encrypted at rest and only used server-side to call AWS Cost
          Explorer. Requires an IAM user with <code>ce:GetCostAndUsage</code> and{" "}
          <code>sts:GetCallerIdentity</code> permissions.
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>
            <Slack size={16} />
            Slack alerts
          </h2>
        </div>
        <form onSubmit={handleSaveWebhook} className="settings-form">
          <label className="auth-field">
            <Link2 size={15} />
            <input
              type="text"
              placeholder="Slack incoming webhook URL"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
            />
          </label>
          {webhookSaved && (
            <div className="status-line">
              <CheckCircle2 size={13} />
              Saved. Anomaly alerts will now post to this webhook.
            </div>
          )}
          <div className="card-actions">
            <button type="submit" className="btn" disabled={savingWebhook}>
              {savingWebhook ? "Saving…" : "Save webhook"}
            </button>
          </div>
        </form>
        <div className="settings-note">
          Get a webhook URL from Slack: api.slack.com/apps → Create New App → From
          scratch → Incoming Webhooks → Add New Webhook to Workspace.
        </div>
      </div>
    </div>
  );
}
