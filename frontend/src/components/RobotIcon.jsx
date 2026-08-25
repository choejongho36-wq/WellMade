function RobotIcon({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 240 240">
      <rect x="52" y="66" width="136" height="122" rx="34" fill="none" stroke="#fff" strokeWidth="10" />
      <line x1="120" y1="66" x2="120" y2="46" stroke="#fff" strokeWidth="9" strokeLinecap="round" />
      <circle cx="120" cy="40" r="10" fill="#fff" />
      <rect x="40" y="82" width="160" height="26" rx="13" fill="#fff" />
      <circle cx="93" cy="142" r="14" fill="#fff" />
      <circle cx="147" cy="142" r="14" fill="#fff" />
      <line x1="98" y1="172" x2="142" y2="172" stroke="#fff" strokeWidth="9" strokeLinecap="round" />
    </svg>
  )
}

export default RobotIcon
