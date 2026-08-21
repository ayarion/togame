// Anthropic の SSE と同じ形を返すだけのニセ Worker。streaming パーサの検証用。
const http = require("http");

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "content-type,x-togame-key",
  "access-control-allow-methods": "POST,OPTIONS",
};

http.createServer((req, res) => {
  if (req.method === "OPTIONS") { res.writeHead(204, CORS); return res.end(); }
  if (req.method !== "POST")    { res.writeHead(405, CORS); return res.end("POST only"); }

  let body = "";
  req.on("data", c => body += c);
  req.on("end", () => {
    console.log("---- received ----");
    try { console.log(JSON.stringify(JSON.parse(body), null, 2)); } catch (e) { console.log(body); }

    res.writeHead(200, { ...CORS, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" });
    const send = (o) => res.write("event: " + o.type + "\ndata: " + JSON.stringify(o) + "\n\n");

    send({ type: "message_start", message: { id: "msg_mock" } });
    // thinking ブロックも混ぜて、text_delta だけ拾えているか確かめる
    send({ type: "content_block_start", index: 0, content_block: { type: "thinking", thinking: "" } });
    send({ type: "content_block_delta", index: 0, delta: { type: "thinking_delta", thinking: "これは拾ってはいけない" } });
    send({ type: "content_block_stop", index: 0 });
    send({ type: "content_block_start", index: 1, content_block: { type: "text", text: "" } });

    const chunks = ["3回目やん。", "5分だけって", "決めてから開く？"];
    let i = 0;
    const tick = setInterval(() => {
      if (i < chunks.length) {
        send({ type: "content_block_delta", index: 1, delta: { type: "text_delta", text: chunks[i++] } });
      } else {
        clearInterval(tick);
        send({ type: "content_block_stop", index: 1 });
        send({ type: "message_delta", delta: { stop_reason: "end_turn" } });
        send({ type: "message_stop" });
        res.end();
      }
    }, 120);
  });
}).listen(8124, () => console.log("mock agent on http://localhost:8124"));
