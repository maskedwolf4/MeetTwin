import Twin from '@/components/twin';

export default function Home() {
  return (
    <main className="min-h-screen bg-[#070b12] px-3 py-3 sm:px-5 sm:py-5 lg:px-8">
      <div className="mx-auto h-[calc(100vh-24px)] max-w-[1440px] overflow-hidden rounded-[24px] border border-white/10 bg-[#0b1018] shadow-[0_24px_80px_rgba(0,0,0,.45)] sm:h-[calc(100vh-40px)]">
        <Twin />
      </div>
    </main>
  );
}