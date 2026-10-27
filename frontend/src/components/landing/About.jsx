import { ArrowRight, Eye, HardDrive, ShieldCheck } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import Reveal from './Reveal'
import { PrimaryAction, SectionHeading } from './ui'

const PRINCIPLES = [
  { icon: HardDrive, title: 'Local-first', text: 'Video, faces and alerts stay on your computer. No cloud account, no subscription, no third party watching your cameras.' },
  { icon: Eye, title: 'Explainable', text: 'No mysterious "AI says so". Each alert names the rule that fired and the numbers behind it, with a snapshot and the recording.' },
  { icon: ShieldCheck, title: 'Honest', text: 'Face recognition is statistical and night detection is weaker — the system says "not sure" instead of guessing, and documents its limits.' },
]

const STACK = ['Python', 'FastAPI', 'OpenCV', 'YOLOv8', 'SQLite', 'React', 'Vite', 'Tailwind CSS']

export default function About() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  return (
    <section id="about" className="relative py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <Reveal>
          <SectionHeading eyebrow="About the project" title="A smarter way to watch over your home">
            Smart AI-Based Home CCTV Surveillance System is a college project that turns ordinary cameras into an assistant that watches for you and tells you what matters.
          </SectionHeading>
        </Reveal>

        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {PRINCIPLES.map(({ icon: Icon, title, text }, i) => (
            <Reveal key={title} delay={i * 90}>
              <div className="glass h-full rounded-2xl p-6">
                <Icon className="h-6 w-6 text-sky-300" />
                <h3 className="mt-4 text-lg font-semibold text-slate-50">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{text}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-14">
          <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Built with</p>
          <ul className="mt-4 flex flex-wrap justify-center gap-2.5">
            {STACK.map((item) => (
              <li key={item} className="glass rounded-lg px-3.5 py-1.5 text-sm font-medium text-slate-300">
                {item}
              </li>
            ))}
          </ul>
        </Reveal>

        <Reveal className="mt-20">
          <div className="relative overflow-hidden rounded-3xl border border-sky-400/20 bg-gradient-to-br from-sky-500/15 via-blue-600/10 to-transparent p-10 text-center sm:p-14">
            <div className="pointer-events-none absolute -top-24 left-1/2 h-48 w-96 -translate-x-1/2 rounded-full bg-sky-400/20 blur-3xl" />
            <h3 className="relative text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">Ready to see your cameras think?</h3>
            <p className="relative mx-auto mt-3 max-w-xl text-slate-400">Sign in to open the live dashboard with your cameras, events, recordings and alerts.</p>
            <div className="relative mt-8 flex justify-center">
              <PrimaryAction to={signedIn ? '/dashboard' : '/login'}>
                {signedIn ? 'Open Dashboard' : 'Get Started'}
                <ArrowRight className="h-4 w-4" />
              </PrimaryAction>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
