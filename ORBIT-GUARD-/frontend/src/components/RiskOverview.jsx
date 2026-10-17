const risks = [
  {
    label: "Critical",
    count: 3,
    className: "critical"
  },
  {
    label: "High",
    count: 12,
    className: "high"
  },
  {
    label: "Medium",
    count: 47,
    className: "medium"
  },
  {
    label: "Low",
    count: 2421,
    className: "low"
  }
];

export default function RiskOverview() {
  return (
    <section className="risk-section">

      <div className="section-title">
        <span>RISK OVERVIEW</span>
      </div>

      <div className="risk-list">

        {risks.map((risk) => (
          <div
            className={`risk-card ${risk.className}`}
            key={risk.label}
          >

            <div className="risk-name">
              <span className="risk-dot"></span>
              {risk.label}
            </div>

            <strong>{risk.count}</strong>

          </div>
        ))}

      </div>

    </section>
  );
}