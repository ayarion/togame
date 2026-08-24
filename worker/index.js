/* トガメのエージェント用プロキシ。

   既定は Cloudflare Workers AI（無料枠 10,000ニューロン/日）。
   トガメ1回ぶんは約27ニューロンなので、1日およそ370回まで無料で収まる。
   「使うたびに金が減る」感覚を消すのが目的（課金を気にして理由を偽る問題への対処）。

   PROVIDER を "anthropic" に変えると、従来どおり Claude を叩く形に戻せる。

   デプロイ:
     npx wrangler deploy
     npx wrangler secret put TOGAME_SECRET      # 自分で決める合言葉。トガメの設定にも同じものを入れる
     npx wrangler secret put ANTHROPIC_API_KEY  # PROVIDER="anthropic" のときだけ必要

   合言葉は、このWorkerを他人に勝手に使われるのを防ぐためのもの。 */

const PROVIDER = "workers-ai";   // "workers-ai" | "anthropic"

/* Workers AI のモデル。入力24,545 / 出力77,273 ニューロン per 1Mトークン。
   他の候補: @cf/mistralai/mistral-small-3.1-24b-instruct（入力31,876 / 出力50,488） */
const CF_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct";

const ANTHROPIC_MODEL = "claude-haiku-4-5";

/* Opus 5 / Sonnet 5 系だけが受け付けるオプションがある。
   Haiku 4.5 に effort や fallbacks を送ると 400 で落ちるので、モデルで切り替える */
const IS_FRONTIER = /^claude-(opus|sonnet|fable)-(5|4-[678])/.test(ANTHROPIC_MODEL);

/* ここに載っていないオリジンからは叩けない */
const ALLOWED_ORIGINS = [
  "https://tsukuriba.org",
  "http://localhost:8123",   // ローカル検証用
];

function corsHeaders(origin){
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "access-control-allow-origin": allow,
    "access-control-allow-headers": "content-type,x-togame-key",
    "access-control-allow-methods": "POST,OPTIONS",
    "vary": "origin",
  };
}

const sseHeaders = h => ({
  ...h,
  "content-type": "text/event-stream; charset=utf-8",
  "cache-control": "no-cache",
});

/* ---------------- Workers AI ---------------- */

/* Workers AI は data: {"response":"..."} 形式で流してくる。
   トガメ側（index.html の askAgent）は Anthropic の text_delta 形式を読むので、
   ここで詰め替える。こうしておけば、提供元を変えてもページ側は一切触らなくていい */
function toAnthropicSSE(cfStream){
  /* マルチバイト文字がチャンク境界で割れるので、デコーダーは使い回して
     {stream:true} で継ぎ目を持ち越させる。チャンクごとに使い捨てにすると
     割れた文字が壊れ、その行のJSON.parseが失敗して丸ごと捨てられ、
     結果として数字などがごっそり欠ける（実際にそのバグを踏んだ） */
  const dec = new TextDecoder();
  const enc = new TextEncoder();
  let buf = "";
  return cfStream.pipeThrough(new TransformStream({
    transform(chunk, ctrl){
      /* Workers AI はモデルによって {"response":"..."} 形式と、OpenAI互換の
         {"choices":[{"delta":{"content":"..."}}]} 形式のどちらかで返す。両対応する */
      buf += dec.decode(chunk, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();                     // 行の途中は次の塊まで持ち越す
      for(const line of lines){
        const t = line.trim();
        if(!t.startsWith("data:")) continue;
        const payload = t.slice(5).trim();
        if(payload === "[DONE]" || !payload) continue;
        let ev;
        try{ ev = JSON.parse(payload); }catch(e){ continue; }
        /* Workers AI は数字トークンだけ response を数値型で返してくる
           （例: {"response":14,"choices":[{"delta":{"content":"14"}}]}）。
           文字列だけ通す判定にしていたため、数字がごっそり欠けていた。
           choices 側は常に文字列なのでそちらを優先し、無い場合だけ
           response を使って String() で受け止める */
        const raw = (ev.choices && ev.choices[0] && ev.choices[0].delta
          && ev.choices[0].delta.content != null)
          ? ev.choices[0].delta.content
          : ev.response;
        if(raw == null) continue;
        const text = String(raw);
        if(text === "") continue;
        ctrl.enqueue(enc.encode("data: " + JSON.stringify({
          type: "content_block_delta",
          index: 0,
          delta: { type: "text_delta", text },
        }) + "\n\n"));
      }
    },
  }));
}

async function runWorkersAI(env, system, user, h){
  if(!env.AI){
    return new Response("AIバインディングが未設定（wrangler.toml の [ai] を確認）", { status:500, headers:h });
  }
  try{
    const stream = await env.AI.run(CF_MODEL, {
      messages: [
        { role: "system", content: system },
        { role: "user",   content: user },
      ],
      max_tokens: 512,
      /* 既定のままだと無難で定型的な文になりやすいので、少し散らす */
      temperature: 0.85,
      stream: true,
    });
    return new Response(toAnthropicSSE(stream), { headers: sseHeaders(h) });
  }catch(e){
    /* 設定画面のテストボタンで中身が見えるように、そのまま返す */
    return new Response("Workers AI エラー: " + ((e && e.message) || e), { status:500, headers:h });
  }
}

/* ---------------- Anthropic（戻したいとき用） ---------------- */

function anthropicHeaders(env){
  const h = {
    "content-type": "application/json",
    "x-api-key": env.ANTHROPIC_API_KEY.trim(),
    "anthropic-version": "2023-06-01",
  };
  if(IS_FRONTIER) h["anthropic-beta"] = "server-side-fallback-2026-07-01";
  return h;
}

function anthropicPayload(system, user){
  const p = {
    model: ANTHROPIC_MODEL,
    max_tokens: 1000,
    stream: true,
    system,
    messages: [{ role: "user", content: user }],
  };
  if(IS_FRONTIER){
    p.output_config = { effort: "low" };
    p.fallbacks = "default";
  }
  return p;
}

async function runAnthropic(env, system, user, h){
  if(!env.ANTHROPIC_API_KEY){
    return new Response("ANTHROPIC_API_KEY が未設定", { status:500, headers:h });
  }
  const upstream = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: anthropicHeaders(env),
    body: JSON.stringify(anthropicPayload(system, user)),
  });
  if(!upstream.ok){
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { ...h, "content-type": "application/json" },
    });
  }
  return new Response(upstream.body, { headers: sseHeaders(h) });
}

/* ---------------- 入口 ---------------- */

export default {
  async fetch(req, env){
    const h = corsHeaders(req.headers.get("origin") || "");

    if(req.method === "OPTIONS") return new Response(null, { status:204, headers:h });

    if(req.method !== "POST")    return new Response("POSTだけ", { status:405, headers:h });
    if(req.headers.get("x-togame-key") !== env.TOGAME_SECRET)
      return new Response("合言葉が違う", { status:401, headers:h });

    let body;
    try{ body = await req.json(); }
    catch(e){ return new Response("JSONが読めない", { status:400, headers:h }); }

    const system = String(body.system || "").slice(0, 8000);
    const user   = String(body.user   || "").slice(0, 8000);
    if(!user) return new Response("userが空", { status:400, headers:h });

    return PROVIDER === "anthropic"
      ? runAnthropic(env, system, user, h)
      : runWorkersAI(env, system, user, h);
  },
};
