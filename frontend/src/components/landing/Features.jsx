import { Film, Lock, Moon, Radar, ScanEye, ScanFace } from 'lucide-react'
import Reveal from './Reveal'
import { SectionHeading } from './ui'

const FEATURES = [
  {
    icon: ScanEye,
    title: 'AI person detection',
    text: 'YOLOv8 finds people in the picture, not just "something moved". Each detection carries a confidence score and a box you can see on the live feed.',
    tags: ['YOLOv8', 'Live boxes', 'Confidence scores'],
  },
  {
    icon: ScanFace,
    title: 'Face recognition',
    text: 'Register family members and the system labels every face known, unknown or not sure — and never guesses when a face is small, dark or turned away.',
    tags: ['Known / unknown', '3 confirmations', 'Private on-device data'],
  },
  {
    icon: Film,
    title: 'Motion-triggered recording',
    text: 'Cameras record only when something happens. Clips are saved as H.264 video with a searchable event history you can filter, play, seek and download.',
    tags: ['H.264 MP4', 'Event history', 'Crash-safe'],
  },
  {
    icon: Radar,
    title: 'Suspicious-activity detection',
    text: 'Draw restricted zones and set clear rules: intrusion, loitering, repeated entry and security hours. Every alert states which rule fired and why.',
    tags: ['Restricted zones', 'Loitering', 'Repeated entry'],
  },
  {
    icon: Moon,
    title: 'Night surveillance',
    text: 'Low-light and infrared video is detected automatically and marked NIGHT MODE. Detection still works in the dark, and recordings are never altered.',
    tags: ['Low-light', 'Infrared aware', 'Honest limits'],
  },
  {
    icon: Lock,
    title: 'Secure local monitoring',
    text: 'Everything runs on your own machine. Login, roles and protected streams keep it private, and remote access is designed for a VPN or HTTPS proxy.',
    tags: ['Login + roles', 'No cloud', 'Remote-ready'],
  },
]

export default function Features() {
  return (
    <section id="features" className="relative py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <Reveal>
          <SectionHeading eyebrow="Features" title="Everything a modern security system should do">
            One pipeline from camera to alert — built from proven computer-vision components and designed to be explainable, not mysterious.
          </SectionHeading>
        </Reveal>

        <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text, tags }, i) => (
            <Reveal key={title} delay={(i % 3) * 90}>
              <article className="glass group relative h-full overflow-hidden rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:border-sky-400/40 hover:shadow-[0_20px_60px_-20px_rgba(56,189,248,0.45)]">
                <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-sky-500/0 blur-3xl transition-all duration-500 group-hover:bg-sky-500/25" />
                <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500/25 to-blue-600/10 text-sky-300 ring-1 ring-sky-400/20 transition-transform duration-300 group-hover:scale-110">
                  <Icon className="h-6 w-6" />
                </span>
                <h3 className="mt-5 text-lg font-semibold text-slate-50">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{text}</p>
                <ul className="mt-5 flex flex-wrap gap-2">
                  {tags.map((t) => (
                    <li key={t} className="rounded-md bg-white/[0.05] px-2 py-1 text-[11px] font-medium text-slate-400">
                      {t}
                    </li>
                  ))}
                </ul>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
