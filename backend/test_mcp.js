const {spawn} = require("child_process");
const proc = spawn("npx", ["-y", "@maton/mcp", "google-sheet", "--agent", "--api-key=GFxw--Qmh_fTvOAtjLlgH-XuKibQUw6xBlnX3LyEAl59Qg1ISdXHdaeb52WlUisuB0TEBsuM4UZuoQG7vqzCNS6ZJ9wJMXMK48E"]);

let stdoutBuf = "";
let stderrBuf = "";

proc.stderr.on("data", d => { stderrBuf += d.toString(); process.stderr.write(d); });
proc.stdout.on("data", d => { stdoutBuf += d.toString(); console.error("STDOUT CHUNK:", JSON.stringify(d.toString())); });

function send(obj) {
  const msg = JSON.stringify(obj);
  const frame = "Content-Length: " + Buffer.byteLength(msg) + "\r\n\r\n" + msg;
  console.error("SENDING:", msg);
  proc.stdin.write(frame);
}

setTimeout(() => send({jsonrpc:"2.0",id:1,method:"initialize",params:{protocolVersion:"2024-11-05",capabilities:{},clientInfo:{name:"test",version:"1.0"}}}), 3000);
setTimeout(() => { send({jsonrpc:"2.0",method:"notifications/initialized",params:{}}); send({jsonrpc:"2.0",id:2,method:"tools/list",params:{}}); }, 4000);
setTimeout(() => { console.error("FINAL STDOUT:", JSON.stringify(stdoutBuf)); console.error("FINAL STDERR:", JSON.stringify(stderrBuf)); proc.kill(); }, 15000);