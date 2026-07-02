import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  DollarSign,
  Server,
  TrendingUp,
  Database,
  BarChart3,
  Activity,
  AlertCircle,
} from "lucide-react";
import { api, ServiceTotal, DailyTotal } from "../api/client";

const BAR_COLORS = ["#111111", "#3d3d3d", "#666666", "#8f8f8f", "#b3b3b3", "#d6d6d6"];

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div style={{ color: "#6b6f76", marginBottom: 4 }}>{label}</div>
      <div style={{ fontWeight: 700 }}>${Number(payload[0].value).toFixed(2)}</div>
    </div>
  );
}

export default function Dashboard() {
  const [byService, setByService] = useState<ServiceTotal[]>([]);
  const [trend, setTrend] = useState<DailyTotal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [services, dailyTrend] = await Promise.all([
        api.costsByService(),
        api.costsTrend(),
      ]);
      setByService(services);
      setTrend(dailyTrend);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSeed = async () => {
    setSeeding(true);
    setError(null);
    try {
      await api.seedCosts();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSeeding(false);
    }
  };

  const hasData = byService.length > 0;
  const totalSpend = byService.reduce((sum, s) => sum + s.total_usd, 0);
  const topService = byService.length
    ? [...byService].sort((a, b) => b.total_usd - a.total_usd)[0]
    : null;
  const avgDaily = trend.length
    ? trend.reduce((sum, d) => sum + d.total_usd, 0) / trend.length
    : 0;

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>
            <Database size={16} />
            Cost data
          </h2>
          <div className="card-actions">
            <button className="btn secondary" onClick={handleSeed} disabled={seeding}>
              <Activity size={14} />
              {seeding ? "Seeding…" : "Seed mock AWS cost data"}
            </button>
          </div>
        </div>
        {error && (
          <div className="status-line error">
            <AlertCircle size={13} />
            {error}
          </div>
        )}
      </div>

      {!hasData && !loading && (
        <div className="card">
          <div className="empty-state">
            <BarChart3 size={32} />
            <div>No cost data yet. Click "Seed mock AWS cost data" above to generate it.</div>
          </div>
        </div>
      )}

      {hasData && (
        <>
          <div className="stats-row">
            <div className="stat-card">
              <div className="stat-icon">
                <DollarSign size={17} />
              </div>
              <div className="stat-label">Total spend</div>
              <div className="stat-value">${totalSpend.toFixed(2)}</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">
                <Server size={17} />
              </div>
              <div className="stat-label">Top service</div>
              <div className="stat-value">{topService?.service ?? "—"}</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">
                <TrendingUp size={17} />
              </div>
              <div className="stat-label">Avg. daily spend</div>
              <div className="stat-value">${avgDaily.toFixed(2)}</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">
                <BarChart3 size={17} />
              </div>
              <div className="stat-label">Services tracked</div>
              <div className="stat-value">{byService.length}</div>
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-header">
                <h2>
                  <BarChart3 size={16} />
                  Total spend by service
                </h2>
              </div>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={byService}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.07)" vertical={false} />
                  <XAxis dataKey="service" stroke="#9a9ea5" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#9a9ea5" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
                  <Bar dataKey="total_usd" radius={[6, 6, 0, 0]}>
                    {byService.map((_, i) => (
                      <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <div className="card-header">
                <h2>
                  <TrendingUp size={16} />
                  Daily spend trend
                </h2>
              </div>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trend}>
                  <defs>
                    <linearGradient id="trendLine" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#111111" />
                      <stop offset="100%" stopColor="#8f8f8f" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.07)" vertical={false} />
                  <XAxis dataKey="date" stroke="#9a9ea5" fontSize={11} tick={false} axisLine={false} />
                  <YAxis stroke="#9a9ea5" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(0,0,0,0.12)" }} />
                  <Line
                    type="monotone"
                    dataKey="total_usd"
                    stroke="url(#trendLine)"
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ r: 5, fill: "#111111" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
