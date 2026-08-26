function RobotIcon({ size = 34, color = '#fff' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 240 240">
      <rect x="52" y="66" width="136" height="122" rx="34" fill="none" stroke={color} strokeWidth="10" />
      <line x1="120" y1="66" x2="120" y2="46" stroke={color} strokeWidth="9" strokeLinecap="round" />
      <circle cx="120" cy="40" r="10" fill={color} />
      <rect x="40" y="82" width="160" height="26" rx="13" fill={color} />
      <circle cx="93" cy="142" r="14" fill={color} />
      <circle cx="147" cy="142" r="14" fill={color} />
      <line x1="98" y1="172" x2="142" y2="172" stroke={color} strokeWidth="9" strokeLinecap="round" />
    </svg>
  )
}

export default RobotIcon
