import { Bell, Camera, Move, ScanEye, ScanFace, Shapes } from 'lucide-react'
import Reveal from './Reveal'
import { SectionHeading } from './ui'

const STEPS = [
  { icon: Camera, title: 'Capture', text: 'Webcams, RTSP / IP cameras, HTTP streams or video files — each camera runs in its own thread, so one failure never stops the others.' },
  { icon: Move, title: 'Detect motion', text: 'OpenCV background subtraction wakes the system only when the scene changes. Lighting flicker and shadows are filtered out.' },
  { icon: ScanEye, title: 'Find people', text: 'While motion is happening, YOLOv8 looks for people a few times per second. Idle scenes cost almost nothing.' },
  { icon: ScanFace, title: 'Recognize faces', text: 'Each person’s face becomes a 128-number signature compared with the people you registered: known, unknown, or not sure.' },
  { icon: Shapes, title: 'Apply the rules', text: 'Zones, loitering, repeated entry, security hours and night conditions turn detections into clearly explained events.' },
  { icon: Bell, title: 'Alert & record', text: 'A snapshot, a recording and an alert with severity appear on your dashboard in real time — and by email if you enable it.' },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="relative border-y border-white/[0.06] bg-gradient-to-b from-white/[0.02] to-transparent py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <Reveal>
          <SectionHeading eyebrow="How it works" title="From camera frame to explained alert">
            Cheap checks first, heavy AI second. That keeps several cameras running smoothly on an ordinary computer.
          </SectionHeading>
        </Reveal>

        <ol className="relative mt-16 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <Reveal key={title} as="li" delay={(i % 3) * 90} className="relative">
              <div className="flex items-center gap-4">
                <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500/25 to-blue-600/10 text-sky-300 ring-1 ring-sky-400/25">
                  <Icon className="h-6 w-6" />
                  <span className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-sky-500 text-[11px] font-bold text-white shadow-lg shadow-sky-500/40">
                    {i + 1}
                  </span>
                </span>
                <h3 className="text-lg font-semibold text-slate-50">{title}</h3>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-400">{text}</p>
              {i < STEPS.length - 1 && (i + 1) % 3 !== 0 && (
                <span className="absolute right-[-1.25rem] top-7 hidden h-px w-8 bg-gradient-to-r from-sky-400/50 to-transparent lg:block" />
              )}
            </Reveal>
          ))}
        </ol>

        <Reveal className="mx-auto mt-16 max-w-3xl">
          <div className="glass rounded-2xl p-5 text-center text-sm text-slate-400">
            <span className="font-mono text-xs text-sky-300">frame → motion → YOLO → face → rules → alert</span>
            <p className="mt-2">Recordings always contain the raw, untouched video. Overlays such as boxes and zones are drawn only on the live copy.</p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
