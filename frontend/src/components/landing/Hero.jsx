import { ArrowRight, ChevronDown, Compass } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import DashboardPreview from './DashboardPreview'
import Reveal from './Reveal'
import { GhostAction, PrimaryAction } from './ui'

// Real capabilities of this system (nothing here is a made-up statistic).
const CAPABILITIES = ['Live multi-camera monitoring', 'YOLOv8 person detection', 'Face recognition', 'Night & infrared support', 'Explainable alerts', 'Runs on your own computer']

export default function Hero() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  return (
    <section id="top" className="relative overflow-clip pt-28 sm:pt-36">
      {/* background: grid, blue glows, vignette */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="bg-grid absolute inset-0 animate-drift opacity-70 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_30%,black,transparent)]" />
        <div className="absolute left-1/2 top-[-12rem] h-[34rem] w-[60rem] -translate-x-1/2 animate-glow rounded-full bg-sky-500/25 blur-[120px]" />
        <div className="absolute right-[-10rem] top-40 h-96 w-96 rounded-full bg-blue-700/20 blur-[110px]" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#05070b] to-transparent" />
      </div>

      <div className="mx-auto max-w-7xl px-4 text-center sm:px-6 lg:px-8">
        <Reveal>
          <span className="glass inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium text-sky-200">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            AI-powered home surveillance · 100% local
          </span>
        </Reveal>

        <Reveal delay={80}>
          <h1 className="mx-auto mt-7 max-w-4xl text-5xl font-semibold leading-[1.05] tracking-tight text-slate-50 sm:text-6xl lg:text-7xl">
            Intelligent Security.
            <br />
            <span className="text-gradient">Powered by AI.</span>
          </h1>
        </Reveal>

        <Reveal delay={160}>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-400">
            Monitor every camera in real time. Detect people with YOLO, recognize the faces you know, keep watching after dark, and get alerts that
            explain exactly <em className="not-italic text-slate-200">what</em> was seen and <em className="not-italic text-slate-200">why</em> — all processed on your own computer, never in the cloud.
          </p>
        </Reveal>

        <Reveal delay={240} className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <PrimaryAction to={signedIn ? '/dashboard' : '/login'}>
            {signedIn ? 'Open Dashboard' : 'Get Started'}
            <ArrowRight className="h-4 w-4" />
          </PrimaryAction>
          <GhostAction href="#features">
            <Compass className="h-4 w-4" />
            Explore Features
          </GhostAction>
        </Reveal>

        <Reveal delay={320}>
          <ul className="mx-auto mt-10 flex max-w-3xl flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-slate-500">
            {CAPABILITIES.map((item) => (
              <li key={item} className="flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-sky-400" />
                {item}
              </li>
            ))}
          </ul>
        </Reveal>

        <Reveal delay={400} className="mt-16 pb-20 sm:mt-20">
          <DashboardPreview />
        </Reveal>
        <a href="#features" aria-label="Scroll to features" className="mx-auto -mt-10 mb-8 hidden w-fit text-slate-600 transition-colors hover:text-sky-300 sm:block">
          <ChevronDown className="h-6 w-6 animate-bounce" />
        </a>
      </div>
    </section>
  )
}
