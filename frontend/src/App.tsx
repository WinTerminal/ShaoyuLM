import { useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || busy) return;

    const newMessages: Msg[] = [...messages, { role: "user", content: q }];
    setInput("");
    setBusy(true);
    setMessages([...newMessages, { role: "assistant", content: "" }]);

    try {
      const res = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "shaoyu",
          messages: newMessages,
          stream: true,
          temperature: 0.8,
          max_tokens: 100,
        }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      const append = (text: string) => {
        setMessages((m) => {
          const copy = m.slice();
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, content: last.content + text };
          return copy;
        });
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const evt of events) {
          for (const line of evt.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6).trim();
            if (data === "[DONE]") continue;
            try {
              const obj = JSON.parse(data);
              const content = obj?.choices?.[0]?.delta?.content;
              if (content) append(content);
            } catch {
              // 忽略解析失败
            }
          }
        }
      }
    } catch (e: any) {
      setMessages((m) => {
        const copy = m.slice();
        const last = copy[copy.length - 1];
        copy[copy.length - 1] = { ...last, content: `[请求失败] ${e.message}` };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  function clearAll() {
    setMessages([]);
  }

  return (
    <div className="flex h-screen flex-col bg-[#212121] text-[#ececec]">
      <header className="flex items-center justify-between border-b border-gray-700 px-5 py-3">
        <h1 className="text-lg font-semibold">
          🔥 <span className="text-orange-500">少羽</span> Chat
        </h1>
        <button
          onClick={clearAll}
          className="rounded-lg border border-gray-600 bg-[#2f2f2f] px-3 py-1.5 text-sm hover:bg-[#3a3a3a]"
        >
          清空历史
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <div className="mt-20 text-center text-gray-500">
            <div className="mb-3 text-4xl">🔥</div>
            <div className="text-lg">问啥啥不会，开口就是筷子夹水泥。</div>
          </div>
        )}
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 leading-relaxed ${
                  m.role === "user"
                    ? "bg-[#2563eb] text-white"
                    : "bg-[#2f2f2f] text-[#ececec]"
                }`}
              >
                {m.content ||
                  (busy && i === messages.length - 1 ? "少羽正在张嘴……" : "")}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-gray-700 p-4">
        <div className="mx-auto flex max-w-3xl gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="随便问，少羽都骂你……"
            disabled={busy}
            className="flex-1 rounded-xl bg-[#2f2f2f] px-4 py-3 text-white outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
          />
          <button
            onClick={send}
            disabled={busy}
            className="rounded-xl bg-orange-500 px-6 py-3 font-semibold text-white hover:bg-orange-600 disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
