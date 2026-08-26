function WorkoutIcon({ size = 34, color = '#fff' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 240 240">
      <circle cx="120" cy="52" r="22" fill={color} />
      <rect x="94" y="80" width="52" height="68" rx="22" fill="none" stroke={color} strokeWidth="10" />
      <path d="M94 96 L66 96 L66 58" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M146 96 L174 96 L174 58" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="110" y1="148" x2="104" y2="192" stroke={color} strokeWidth="10" strokeLinecap="round" />
      <line x1="130" y1="148" x2="136" y2="192" stroke={color} strokeWidth="10" strokeLinecap="round" />
    </svg>
  )
}

export default WorkoutIcon
