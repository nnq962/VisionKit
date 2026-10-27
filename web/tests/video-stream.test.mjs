import assert from 'node:assert/strict';
import {test} from 'node:test';
import {VideoStreamStore} from '../src/features/video-stream/stream-store.ts';
import {StreamFailure} from '../src/features/video-stream/webrtc-client.ts';
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
function fixture(limit=4){
 let now=0,next=0;const timers=new Map(),connections=[];
 const env={open:async(id,callbacks,signal,temporaryUrl)=>{const c={id,callbacks,signal,temporaryUrl,closed:false,close(){this.closed=true},status:async()=>({status:'ready',auth:'accepted',codecs:['H264']})};connections.push(c);signal.addEventListener('abort',()=>c.close());return c},random:()=>.5,later:(callback,delay)=>{const id=++next;timers.set(id,{at:now+delay,callback});return id},cancel:id=>timers.delete(id)};
 const store=new VideoStreamStore(env,limit);
 const tick=async(ms)=>{const end=now+ms;for(;;){const due=[...timers.entries()].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].callback();await flush()}now=end};
 const play=(c=connections.at(-1))=>{c.callbacks.status({status:'ready',auth:'accepted',codecs:['H264']});c.callbacks.stream({id:'media'});c.callbacks.state('connected')};
 return{store,env,timers,connections,tick,play};
}
test('multiple consumers and route changes share one peer connection and MediaStream',async()=>{
 const f=fixture(),u1=f.store.subscribe('cam',()=>{}),u2=f.store.subscribe('cam',()=>{});f.store.start('cam');f.store.start('cam');await flush();f.play();const s=f.store.snapshot('cam');u1();u2();f.store.subscribe('cam',()=>{});f.store.start('cam');assert.equal(f.connections.length,1);assert.equal(f.connections[0].closed,false);assert.equal(f.store.snapshot('cam'),s);assert.equal(s.auth,'accepted');f.store.dispose();assert.equal(f.timers.size,0);
});
test('peer failures back off; stale callbacks cannot overwrite current connection',async()=>{
 const f=fixture();f.store.start('cam');await flush();const first=f.connections[0];f.play();first.callbacks.error(new StreamFailure('lost'));assert.equal(first.closed,true);await f.tick(999);assert.equal(f.connections.length,1);await f.tick(1);assert.equal(f.connections.length,2);first.callbacks.stream({id:'old'});assert.equal(f.store.snapshot('cam').mediaStream,null);f.connections[1].callbacks.error(new StreamFailure('lost'));await f.tick(1999);assert.equal(f.connections.length,2);await f.tick(1);assert.equal(f.connections.length,3);f.store.dispose();
});
test('API-proven camera auth failure is terminal; configuration update allows retry',async()=>{
 const f=fixture();f.store.start('cam');await flush();f.connections[0].callbacks.status({status:'error',auth:'rejected',codecs:[],code:'auth_failed',retryable:false,message:'Check password'});assert.equal(f.store.snapshot('cam').auth,'rejected');assert.equal(f.store.snapshot('cam').status,'error');await f.tick(120000);assert.equal(f.connections.length,1);assert.equal(f.timers.size,0);f.store.configurationChanged('cam');await flush();assert.equal(f.connections.length,2);f.store.dispose();
});
test('explicit stop survives routes and configuration updates',async()=>{
 const f=fixture(),u=f.store.subscribe('cam',()=>{});f.store.start('cam');await flush();f.store.stop('cam');u();f.store.configurationChanged('cam');await f.tick(60000);assert.equal(f.store.snapshot('cam').status,'stopped');assert.equal(f.connections.length,1);f.store.start('cam');await flush();assert.equal(f.connections.length,2);f.store.dispose();
});
test('backend heartbeat failures reconnect and online accelerates recovery',async()=>{
 const f=fixture();f.store.start('cam');await flush();f.play();f.connections[0].status=async()=>{throw Error('Offline')};await f.tick(2000);assert.equal(f.store.snapshot('cam').status,'reconnecting');f.store.online();await flush();assert.equal(f.connections.length,2);f.store.dispose();
});
test('late negotiation results are closed after explicit stop',async()=>{
 const f=fixture();let resolve;const c={closed:false,close(){this.closed=true},status:async()=>({status:'ready',auth:'accepted',codecs:[]})};f.env.open=()=>new Promise(done=>resolve=done);f.store.start('cam');f.store.stop('cam');resolve(c);await flush();assert.equal(c.closed,true);assert.equal(f.store.snapshot('cam').status,'stopped');f.store.dispose();
});
test('negotiation timeout, codec errors, limits and disposal reclaim resources',async()=>{
 const f=fixture(2);f.store.start('a');f.store.start('b');f.store.start('c');await flush();assert.equal(f.connections.length,2);assert.equal(f.store.snapshot('c').status,'error');await f.tick(35000);assert.equal(f.connections.length,2);await f.tick(1000);assert.ok(f.connections.length>2);f.store.dispose();assert.ok(f.connections.every(c=>c.closed));assert.equal(f.timers.size,0);const g=fixture();g.store.start('cam');await flush();g.connections[0].callbacks.error(new StreamFailure('Unsupported',false,'unsupported_codec'));await g.tick(60000);assert.equal(g.connections.length,1);g.store.dispose();
});

test('temporary URLs use the unsaved connection flow and remain shared across routes',async()=>{
 const f=fixture();const un=f.store.subscribe('draft',()=>{});
 f.store.startTemporary('draft','rtsp://user:secret@camera/live');await flush();f.play();un();
 f.store.subscribe('draft',()=>{});f.store.start('draft');
 assert.equal(f.connections.length,1);assert.equal(f.connections[0].temporaryUrl,'rtsp://user:secret@camera/live');
 f.store.discardTemporary('draft');assert.equal(f.connections[0].closed,true);
 f.store.start('draft');await flush();assert.equal(f.connections[1].temporaryUrl,undefined);f.store.dispose();
});
test('first temporary check times out without retrying endlessly; established live connections still recover',async()=>{
 const f=fixture();f.store.startTemporary('draft','rtsp://camera/live');await flush();
 await f.tick(35000);assert.equal(f.store.snapshot('draft').status,'error');
 await f.tick(120000);assert.equal(f.connections.length,1);f.store.dispose();
 const g=fixture();g.store.startTemporary('draft','rtsp://camera/live');await flush();g.play();
 g.connections[0].callbacks.error(new StreamFailure('Lost'));await g.tick(1000);assert.equal(g.connections.length,2);g.store.dispose();
});

test('finishing a pipeline can await server viewer cleanup after stopping local transport', async () => {
 const f=fixture();
 f.store.start('cam');await flush();f.play();
 let release;
 const closing=new Promise(resolve=>{release=resolve});
 f.connections[0].close=function(){this.closed=true;return closing};
 let complete=false;
 const stopped=Promise.resolve(f.store.stop('cam')).then(()=>{complete=true});
 assert.equal(f.connections[0].closed,true);
 assert.equal(f.store.snapshot('cam').status,'stopped');
 await flush();assert.equal(complete,false);
 release();await stopped;assert.equal(complete,true);
 assert.equal(f.timers.size,0);
});
