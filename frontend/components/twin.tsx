'use client';

import { useState, useRef, useEffect } from 'react';
import Image from 'next/image';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Send, User, Plus, MessageSquare, MoreHorizontal } from 'lucide-react';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

export default function Twin() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sessionId, setSessionId] = useState<string>('');
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        if (messages.length === 0) return;
        scrollToBottom();
    }, [messages]);

    const sendMessage = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: input,
            timestamp: new Date(),
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: input,
                    session_id: sessionId || undefined,
                }),
            });

            if (!response.ok) throw new Error('Failed to send message');

            const data = await response.json();

            if (!sessionId) {
                setSessionId(data.session_id);
            }

            const assistantMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: data.response,
                timestamp: new Date(),
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (error) {
            console.error('Error:', error);
            // Add error message
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.',
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <div className="flex h-full bg-[#0b1018] text-white">
            <aside className="hidden w-[280px] shrink-0 flex-col border-r border-white/[0.07] bg-[#080c13] md:flex">
                <div className="flex h-20 items-center px-5">
                    <div className="flex items-center gap-3">
                        <div className="grid h-10 w-10 place-items-center overflow-hidden rounded-xl bg-[#176bff] shadow-[0_8px_24px_rgba(23,107,255,.28)]">
                            <Image src="/AIGen.svg" alt="MeetTwin" width={40} height={40} className="h-full w-full object-cover" />
                        </div>
                        <div>
                            <p className="text-[15px] font-semibold tracking-wide">MeetTwin</p>
                            <p className="mt-0.5 text-xs text-slate-500">AI companion</p>
                        </div>
                    </div>
                </div>

                <div className="px-3">
                    <button type="button" onClick={() => setMessages([])} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/[0.09] bg-white/[0.04] px-4 py-3 text-sm font-medium text-slate-200 transition hover:border-[#176bff]/50 hover:bg-[#176bff]/10">
                        <Plus className="h-4 w-4" />New conversation
                    </button>
                </div>

                <div className="mt-6 flex-1 px-3">
                    <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Recent</p>
                    {messages.length > 0 ? (
                        <button type="button" className="flex w-full items-center gap-3 rounded-xl bg-[#176bff]/10 px-3 py-3 text-left text-sm text-slate-200">
                            <MessageSquare className="h-4 w-4 shrink-0 text-[#4e94ff]" />
                            <span className="truncate">Current conversation</span>
                            <MoreHorizontal className="ml-auto h-4 w-4 text-slate-500" />
                        </button>
                    ) : (
                        <p className="px-2 text-sm text-slate-600">No recent conversations</p>
                    )}
                </div>

                <div className="m-3 flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.03] p-3">
                    <div className="grid h-9 w-9 place-items-center rounded-full bg-white text-[#0b1018]"><User className="h-4 w-4" /></div>
                    <div className="min-w-0"><p className="truncate text-sm font-medium">Personal workspace</p><p className="truncate text-xs text-slate-500">MeetTwin account</p></div>
                </div>
            </aside>

            <section className="flex min-w-0 flex-1 flex-col">
                <header className="flex h-20 shrink-0 items-center justify-between border-b border-white/[0.07] px-4 sm:px-7">
                    <div className="flex items-center gap-3">
                        <div className="grid h-10 w-10 place-items-center overflow-hidden rounded-full border border-[#176bff]/40 bg-[#176bff]/10 md:hidden"><Image src="/AIGen.svg" alt="MeetTwin" width={40} height={40} className="h-full w-full object-cover" /></div>
                        <div><h1 className="text-sm font-semibold sm:text-base">MeetTwin</h1><div className="mt-1 flex items-center gap-1.5 text-xs text-slate-500"><span className="h-1.5 w-1.5 rounded-full bg-[#3b82f6] shadow-[0_0_8px_rgba(59,130,246,.9)]" />Online</div></div>
                    </div>
                    <button type="button" aria-label="Conversation options" className="grid h-9 w-9 place-items-center rounded-lg text-slate-500 transition hover:bg-white/[0.06] hover:text-white"><MoreHorizontal className="h-5 w-5" /></button>
                </header>

            {/* Messages */}
            <div className="chat-scroll flex-1 overflow-y-auto px-4 py-6 sm:px-7 lg:px-10">
                <div className="mx-auto max-w-3xl">
                    {messages.length === 0 && (
                        <div className="flex min-h-[420px] flex-col items-center justify-center text-center">
                            <div className="mb-5 grid h-16 w-16 place-items-center overflow-hidden rounded-2xl border border-[#176bff]/30 bg-[#176bff]/10"><Image src="/AIGen.svg" alt="MeetTwin" width={64} height={64} className="h-full w-full object-cover" /></div>
                            <h2 className="text-2xl font-semibold tracking-tight">How can I help you today?</h2>
                            <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">Start a conversation with your AI twin.</p>
                            <button type="button" onClick={() => setInput('Tell me about yourself')} className="mt-7 rounded-full border border-white/[0.09] bg-white/[0.04] px-4 py-2 text-sm text-slate-300 transition hover:border-[#176bff]/50 hover:bg-[#176bff]/10">Tell me about yourself</button>
                        </div>
                    )}

                    <div className="space-y-6">
                        {messages.map((message) => (
                            <div key={message.id} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                {message.role === 'assistant' && <div className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-lg border border-[#176bff]/30 bg-[#176bff]/10"><Image src="/AIGen.svg" alt="MeetTwin" width={32} height={32} className="h-full w-full object-cover" /></div>}
                                <div className={`flex max-w-[82%] flex-col sm:max-w-[72%] ${message.role === 'user' ? 'items-end' : 'items-start'}`}>
                                    <div className={`min-w-0 max-w-full px-4 py-3 text-[15px] leading-7 ${message.role === 'user' ? 'whitespace-pre-wrap rounded-2xl rounded-br-md bg-[#176bff] text-white' : 'rounded-2xl rounded-bl-md border border-white/[0.07] bg-[#111823] text-slate-200'}`}>
                                        {message.role === 'assistant' ? (
                                            <div className="markdown-content">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                                            </div>
                                        ) : (
                                            <p>{message.content}</p>
                                        )}
                                    </div>
                                    <p className="mt-1.5 px-1 text-[10px] text-slate-600">{message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                                </div>
                                {message.role === 'user' && <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white text-[#0b1018]"><User className="h-4 w-4" /></div>}
                            </div>
                        ))}

                        {isLoading && (
                            <div className="flex gap-3">
                                <div className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-lg border border-[#176bff]/30 bg-[#176bff]/10"><Image src="/AIGen.svg" alt="MeetTwin" width={32} height={32} className="h-full w-full object-cover" /></div>
                                <div className="rounded-2xl rounded-bl-md border border-white/[0.07] bg-[#111823] px-4 py-4"><div className="flex gap-1.5"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#77aaff]" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#77aaff] delay-100" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#77aaff] delay-200" /></div></div>
                            </div>
                        )}
                    </div>
                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Input */}
            <div className="shrink-0 px-4 pb-4 pt-2 sm:px-7 sm:pb-5 lg:px-10">
                <div className="mx-auto max-w-3xl">
                    <div className="flex items-end gap-2 rounded-2xl border border-white/[0.10] bg-[#111823] p-2 shadow-[0_12px_40px_rgba(0,0,0,.20)] transition focus-within:border-[#176bff]/60 focus-within:ring-2 focus-within:ring-[#176bff]/10">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyPress}
                            placeholder="Message MeetTwin..."
                            className="h-11 min-w-0 flex-1 bg-transparent px-3 text-[15px] text-white outline-none placeholder:text-slate-600"
                            disabled={isLoading}
                        />
                        <button
                            type="button"
                            onClick={sendMessage}
                            disabled={!input.trim() || isLoading}
                            aria-label="Send message"
                            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#176bff] text-white shadow-[0_8px_20px_rgba(23,107,255,.24)] transition hover:bg-[#2e79ff] disabled:cursor-not-allowed disabled:opacity-35"
                        >
                            <Send className="h-4 w-4" />
                        </button>
                    </div>
                    <p className="mt-2 text-center text-[10px] text-slate-700">MeetTwin can make mistakes. Verify important information.</p>
                </div>
            </div>
            </section>
        </div>
    );
}
