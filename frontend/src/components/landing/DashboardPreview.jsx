import { Activity, Bell, Film, LayoutDashboard, Moon, OctagonAlert, ShieldAlert, Users, Video, VideoOff } from 'lucide-react'
import { useNow } from '../../hooks/useNow'
import { formatClock } from '../../utils/format'
import { LogoMark } from '../Logo'

// A stylised silhouette; `s` scales it, (x, y) is where its feet stand.
function Person({ x, y, s = 1, fill, className = '' }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <g className={className}>
        <circle cx="0" cy="-38" r="6.5" fill={fill} />
        <path d="M-10 -29 Q0 -34 10 -29 L12 -6 L5 -6 L4 0 L5 22 L-1 22 L0 0 L-1 0 L-2 22 L-8 22 L-5 -6 L-12 -6 Z" fill={fill} />
      </g>
    </g>
  )
}

// The box a detector draws around a person.
function DetectionBox({ x, y, w, h, label, color, className = '' }) {
  const c = 5
  return (
    <g className={className} stroke={color} strokeWidth="1.2" fill="none">
      <path d={`M${x} ${y + c}V${y}H${x + c} M${x + w - c} ${y}H${x + w}V${y + c} M${x + w} ${y + h - c}V${y + h}H${x + w - c} M${x + c} ${y + h}H${x}V${y + h - c}`} strokeWidth="1.8" />
      <rect x={x} y={y} width={w} height={h} strokeOpacity="0.35" />
      <rect x={x} y={y - 11} width={label.length * 4.3 + 8} height="10" fill={color} stroke="none" rx="2" />
      <text x={x + 4} y={y - 3.4} fontSize="7" fontWeight="700" fill="#021018" stroke="none">
        {label}
      </text>
    </g>
  )
}

function Scene({ variant }) {
  if (variant === 'entrance') {
    return (
      <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" className="h-full w-full" aria-hidden="true">
        <defs>
          <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1b2433" />
            <stop offset="1" stopColor="#101826" />
          </linearGradient>
        </defs>
        <rect width="320" height="180" fill="url(#wall)" />
        <rect x="205" y="28" width="62" height="104" rx="3" fill="#0b121d" stroke="#25324a" />
        <circle cx="258" cy="84" r="2" fill="#4f6a94" />
        <rect x="24" y="40" width="70" height="46" rx="3" fill="#16314f" opacity="0.55" />
        <path d="M0 132H320V180H0Z" fill="#0d141f" />
        <path d="M0 132H320" stroke="#2a3a55" />
        <polygon points="132,138 292,138 312,176 112,176" fill="rgb(239 68 68 / 0.16)" stroke="#ef4444" strokeWidth="1.2" strokeDasharray="5 3" />
        <text x="150" y="152" fontSize="7" fontWeight="700" fill="#fca5a5">RESTRICTED · GARAGE</text>
        <Person x={170} y={158} s={1.55} fill="#475a7a" className="animate-walk" />
        <DetectionBox x={142} y={86} w={56} h={76} label="person 94%" color="#38bdf8" className="animate-walk" />
      </svg>
    )
  }
  if (variant === 'street') {
    return (
      <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" className="h-full w-full" aria-hidden="true">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1d2b46" />
            <stop offset="1" stopColor="#3a3552" />
          </linearGradient>
        </defs>
        <rect width="320" height="180" fill="url(#sky)" />
        <path d="M0 96h38V52h46v44h26V68h48v28h40V44h54v52h68v84H0z" fill="#10172a" />
        {[[50, 62], [64, 62], [50, 76], [64, 76], [236, 56], [250, 56], [264, 56], [236, 72], [264, 72]].map(([x, y]) => (
          <rect key={`${x}-${y}`} x={x} y={y} width="7" height="8" fill="#e8b25c" opacity="0.55" />
        ))}
        <rect y="124" width="320" height="56" fill="#0c111c" />
        <path d="M0 150H320" stroke="#26334c" strokeDasharray="14 10" />
        <rect x="20" y="136" width="52" height="20" rx="6" fill="#1f2a40" />
        <Person x={206} y={148} s={0.9} fill="#53688b" className="animate-walk-slow" />
        <DetectionBox x={191} y={113} w={31} h={38} label="person 89%" color="#38bdf8" className="animate-walk-slow" />
        <Person x={250} y={150} s={0.8} fill="#4a5d7d" className="animate-walk" />
      </svg>
    )
  }
  if (variant === 'night') {
    return (
      <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" className="h-full w-full" aria-hidden="true">
        <defs>
          <radialGradient id="ir" cx="0.5" cy="0.55" r="0.75">
            <stop offset="0" stopColor="#3f6f55" />
            <stop offset="1" stopColor="#08130d" />
          </radialGradient>
          <filter id="grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
            <feColorMatrix type="matrix" values="0 0 0 0 0.6  0 0 0 0 1  0 0 0 0 0.7  0 0 0 0.16 0" />
          </filter>
        </defs>
        <rect width="320" height="180" fill="url(#ir)" />
        <path d="M0 120H320V180H0Z" fill="#071009" opacity="0.8" />
        <rect x="40" y="46" width="64" height="74" rx="3" fill="#0d1d14" stroke="#2f5a43" />
        <rect x="230" y="70" width="52" height="50" rx="3" fill="#0d1d14" stroke="#2f5a43" />
        <Person x={160} y={150} s={1.3} fill="#8fd4a8" className="animate-walk-slow" />
        <DetectionBox x={136} y={88} w={48} h={66} label="person 81%" color="#4ade80" className="animate-walk-slow" />
        <rect width="320" height="180" filter="url(#grain)" />
      </svg>
    )
  }
  return null
}

function Feed({ name, variant, badges, offline = false }) {
  const now = useNow()
  return (
    <div className="relative aspect-video overflow-hidden rounded-lg border border-white/10 bg-black">
      {offline ? (
        <div className="flex h-full flex-col items-center justify-center gap-1.5 bg-slate-950 text-slate-600">
          <VideoOff className="h-6 w-6" />
          <span className="text-[11px] font-medium">Camera offline · retrying</span>
        </div>
      ) : (
        <Scene variant={variant} />
      )}
      {!offline && <div className="pointer-events-none absolute inset-x-0 top-0 h-1/3 animate-scan bg-gradient-to-b from-transparent via-sky-300/10 to-transparent" />}
      <div className="absolute left-1.5 top-1.5 flex flex-wrap gap-1">
        {badges.map((b) => (
          <span key={b.text} className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${b.cls}`}>
            {b.dot && <span className={`h-1.5 w-1.5 rounded-full ${b.dot}`} />}
            {b.text}
          </span>
        ))}
      </div>
      <div className="absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-black/80 to-transparent px-2 py-1.5 text-[10px]">
        <span className="font-medium text-slate-100">{name}</span>
        <span className="font-mono text-slate-300">{formatClock(now)}</span>
      </div>
    </div>
  )
}

const LIVE = { text: 'LIVE', cls: 'bg-emerald-500/90 text-black', dot: 'bg-black' }
const REC = { text: 'REC', cls: 'bg-red-600/90 text-white', dot: 'bg-white animate-pulse' }

function MiniStat({ icon: Icon, label, value, tone }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.03] px-2.5 py-2">
      <span className={`flex h-7 w-7 items-center justify-center rounded-md ${tone}`}>
        <Icon className="h-3.5 w-3.5" />
      </span>
      <span className="leading-tight">
        <span className="block text-[8px] font-medium uppercase tracking-wide text-slate-500">{label}</span>
        <span className="block text-sm font-semibold tabular-nums text-slate-100">{value}</span>
      </span>
    </div>
  )
}

function AlertRow({ icon: Icon, title, text, severity, tone }) {
  return (
    <div className="flex gap-2.5 rounded-lg border border-white/[0.07] bg-white/[0.03] p-2.5">
      <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${tone}`}>
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 leading-tight">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-100">
          {title}
          <span className="rounded bg-red-500/15 px-1 text-[8px] font-bold text-red-300">{severity}</span>
        </p>
        <p className="mt-0.5 text-[10px] leading-snug text-slate-400">{text}</p>
      </div>
    </div>
  )
}

const SIDE_ICONS = [LayoutDashboard, Video, Bell, Activity, Film, Users]

/**
 * An illustration of the real dashboard (sample data — the real, live
 * dashboard is behind the login). It is drawn with SVG/CSS, so it needs no images.
 */
export default function DashboardPreview() {
  return (
    <div className="relative mx-auto w-full max-w-5xl">
      <div className="absolute -inset-x-10 -inset-y-8 -z-10 rounded-[3rem] bg-sky-500/10 blur-3xl" />

      <div className="glass overflow-hidden rounded-2xl shadow-[0_30px_120px_-20px_rgba(37,99,235,0.45)]" role="img" aria-label="Preview of the Smart CCTV dashboard with sample data">
        {/* window chrome */}
        <div className="flex items-center gap-2 border-b border-white/[0.07] bg-black/30 px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/70" />
          <span className="ml-3 hidden flex-1 rounded-md bg-white/[0.05] px-3 py-1 text-center text-[11px] text-slate-500 sm:block">localhost / dashboard</span>
          <span className="ml-auto rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300 sm:ml-0">
            Sample data
          </span>
        </div>

        <div className="flex">
          <div className="hidden w-12 shrink-0 flex-col items-center gap-3 border-r border-white/[0.07] bg-black/20 py-4 sm:flex">
            <LogoMark className="h-7 w-7" />
            {SIDE_ICONS.map((Icon, i) => (
              <span key={i} className={`flex h-8 w-8 items-center justify-center rounded-lg ${i === 0 ? 'bg-sky-500/15 text-sky-300' : 'text-slate-500'}`}>
                <Icon className="h-4 w-4" />
              </span>
            ))}
          </div>

          <div className="min-w-0 flex-1 space-y-3 p-3 sm:p-4">
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              <MiniStat icon={Video} label="Cameras online" value="3/4" tone="bg-emerald-500/15 text-emerald-400" />
              <MiniStat icon={Users} label="People now" value="2" tone="bg-red-500/15 text-red-400" />
              <MiniStat icon={Activity} label="Events today" value="27" tone="bg-sky-500/15 text-sky-400" />
              <MiniStat icon={Bell} label="Unread alerts" value="3" tone="bg-amber-500/15 text-amber-400" />
            </div>

            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_15rem]">
              <div className="grid grid-cols-2 gap-2.5">
                <Feed name="Front Entrance" variant="entrance" badges={[LIVE, REC, { text: 'UNKNOWN', cls: 'bg-red-600/90 text-white' }]} />
                <Feed name="Street View" variant="street" badges={[LIVE, REC]} />
                <Feed name="Garage · Night" variant="night" badges={[LIVE, { text: 'NIGHT · IR', cls: 'bg-indigo-600/90 text-white' }]} />
                <Feed name="Back Garden" offline badges={[{ text: 'OFFLINE', cls: 'bg-slate-700/90 text-slate-300' }]} />
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Active alerts</p>
                <AlertRow icon={ShieldAlert} tone="bg-red-500/15 text-red-400" severity="HIGH" title="Unknown person" text="Front Entrance · confirmed after 3 sightings, snapshot saved" />
                <AlertRow icon={OctagonAlert} tone="bg-orange-500/15 text-orange-400" severity="HIGH" title="Restricted area" text="Person remained in 'Garage' for 32 seconds (limit 30)" />
                <AlertRow icon={VideoOff} tone="bg-amber-500/15 text-amber-400" severity="MEDIUM" title="Camera offline" text="Back Garden stopped responding" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* floating callouts */}
      <div className="glass absolute top-24 hidden animate-float items-center gap-2.5 rounded-xl px-3.5 py-2.5 shadow-xl 2xl:flex 2xl:-left-44">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-300">
          <Moon className="h-4 w-4" />
        </span>
        <span className="text-xs leading-tight">
          <span className="block font-semibold text-slate-100">Night mode active</span>
          <span className="text-slate-400">Infrared feed detected</span>
        </span>
      </div>
      <div className="glass absolute bottom-24 hidden animate-float items-center gap-2.5 rounded-xl px-3.5 py-2.5 shadow-xl [animation-delay:-3s] 2xl:flex 2xl:-right-44">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-500/20 text-red-300">
          <ShieldAlert className="h-4 w-4" />
        </span>
        <span className="text-xs leading-tight">
          <span className="block font-semibold text-slate-100">Alert · High severity</span>
          <span className="text-slate-400">Unknown person at the entrance</span>
        </span>
      </div>
      <p className="mt-4 text-center text-xs text-slate-400">Illustrative preview with sample data, not a live feed. The real dashboard shows your own cameras and only real figures.</p>
    </div>
  )
}
