import {useEffect,useRef,useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {api,getSessionPolicy,revokeSession,setAuth,type SessionPolicy} from '../services/api';
import {useAuth} from './AuthProvider';

export const IDLE_MESSAGE='Your session expired due to inactivity.';
export function deadlineFromPolicy(policy:SessionPolicy){return Date.now()+Math.max(0,Math.min(policy.idle_timeout_seconds*1000,Date.parse(policy.idle_expires_at)-Date.parse(policy.server_time)))}

export default function IdleSession(){
 const {user}=useAuth();const navigate=useNavigate();const [remaining,setRemaining]=useState<number|null>(null);const [warning,setWarning]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [dirty,setDirty]=useState(false);
 const dialog=useRef<HTMLDivElement>(null);const stay=useRef<()=>Promise<void>>(async()=>{});const logout=useRef<(idle:boolean)=>void>(()=>{});
 useEffect(()=>{
  if(!warning)return;const previous=document.activeElement as HTMLElement|null;dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();return()=>{if(previous?.isConnected)previous.focus()};
 },[warning]);
 useEffect(()=>{
  if(!user){setWarning(false);return}
  let policy:SessionPolicy|null=getSessionPolicy(), deadline=policy?deadlineFromPolicy(policy):0, ended=false, pending=false,lastSent=0, warned=false;
  const channel=typeof BroadcastChannel!=='undefined'?new BroadcastChannel('annotation-session'):null;
  const send=(value:object)=>{channel?.postMessage(value);try{localStorage.setItem('annotation-session-event',JSON.stringify({...value,nonce:Math.random()}))}catch{/* BroadcastChannel remains available. */}};
  const apply=(next:SessionPolicy,broadcast=false)=>{if(ended)return;policy=next;deadline=deadlineFromPolicy(next);if(broadcast)send({kind:'activity',id:next.id,deadline});check()};
  const end=(idle:boolean,remote=false)=>{
   if(ended)return;ended=true;const id=policy?.id;setAuth(null);setWarning(false);
   if(id&&!remote){send({kind:'logout',id,idle});
    const revoke=async()=>{try{const key='annotation-ended-'+id;let sent=false;try{sent=!!localStorage.getItem(key);if(!sent)localStorage.setItem(key,'1')}catch{/* Storage disabled: still revoke. */}if(!sent)await revokeSession(id)}catch{/* Server idle enforcement remains authoritative offline. */}};
    if(navigator.locks)void navigator.locks.request('annotation-logout',revoke);else void revoke();
   }
   if(idle)sessionStorage.setItem('annotation-idle-message',IDLE_MESSAGE);
   navigate('/login',{replace:true});
  };
  function check(){if(ended||!policy)return;const left=deadline-Date.now();if(left<=0){end(true);return}warned=left<=policy.warning_seconds*1000;setWarning(warned);setRemaining(Math.ceil(left/1000))}
  const activity=async(force=false)=>{
   check();if(ended||!policy||pending||(!force&&warned)||(!force&&Date.now()-lastSent<15000))return;
   pending=true;lastSent=Date.now();if(force){setBusy(true);setError('')}
   try{const result=await api.post<SessionPolicy>('/auth/activity');apply(result.data,true)}catch(e:any){if(e.response?.status===401)end(true);else if(force)setError('Unable to confirm your session. Check your connection and retry.')}finally{pending=false;if(force)setBusy(false)}
  };
  stay.current=()=>activity(true);logout.current=(idle)=>end(idle);
  const interaction=(event:Event)=>{if(event.isTrusted)void activity()};
  const receive=(message:any)=>{if(ended||!policy||message?.id!==policy.id)return;if(message.kind==='logout')end(!!message.idle,true);else if(message.kind==='activity'&&Number.isFinite(message.deadline)){deadline=Math.max(deadline,Math.min(message.deadline,Date.now()+policy.idle_timeout_seconds*1000));check()}};
  const storage=(event:StorageEvent)=>{if(event.key==='annotation-session-event'&&event.newValue){try{receive(JSON.parse(event.newValue))}catch{/* Ignore unrelated malformed data. */}}};
  if(channel)channel.onmessage=event=>receive(event.data);
  const sync=()=>{check();if(!ended)void api.get<SessionPolicy>('/auth/session').then(r=>apply(r.data)).catch(()=>{})};
  const visible=()=>{if(document.visibilityState==='visible')sync()};
  const onPolicy=(event:Event)=>apply((event as CustomEvent<SessionPolicy>).detail);
  const onLogout=()=>{if(policy)send({kind:'logout',id:policy.id,idle:false});ended=true};
  const onDirty=(event:Event)=>setDirty(!!(event as CustomEvent).detail);
  const onExpired=()=>end(true);
  window.addEventListener('session-idle-expired',onExpired);
  const events=['pointerdown','keydown','wheel','touchstart'];events.forEach(name=>window.addEventListener(name,interaction,{passive:true,capture:true}));
  window.addEventListener('storage',storage);window.addEventListener('focus',sync);document.addEventListener('visibilitychange',visible);window.addEventListener('session-policy',onPolicy);window.addEventListener('session-logout',onLogout);window.addEventListener('annotation-dirty',onDirty);
  const timer=window.setInterval(check,1000);if(!policy)sync();else check();
  return()=>{ended=true;clearInterval(timer);channel?.close();events.forEach(name=>window.removeEventListener(name,interaction,true));window.removeEventListener('storage',storage);window.removeEventListener('focus',sync);document.removeEventListener('visibilitychange',visible);window.removeEventListener('session-policy',onPolicy);window.removeEventListener('session-logout',onLogout);window.removeEventListener('annotation-dirty',onDirty);window.removeEventListener('session-idle-expired',onExpired)};
 },[user?.id,navigate]);
 if(!user||!warning)return null;
 return <div className="modal-backdrop"><div ref={dialog} className="modal" role="alertdialog" aria-modal="true" aria-labelledby="idle-title" aria-describedby="idle-description" onKeyDown={event=>{if(event.key==='Tab'){const buttons=dialog.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');if(!buttons?.length)return;const first=buttons[0],last=buttons[buttons.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}}}><h2 id="idle-title">Session Expiring Soon</h2><p id="idle-description">You have been inactive. Your session will expire in {Math.floor((remaining??0)/60)}:{String((remaining??0)%60).padStart(2,'0')}.</p><p>{dirty?'You have unsaved annotations. Stay logged in, then save your work.':'Save any unfinished work before your session expires.'} Unsaved changes cannot be saved after logout.</p>{error&&<p role="alert">{error}</p>}<div className="modal-actions"><button disabled={busy} onClick={()=>void stay.current()}>{busy?'Confirming…':'Stay Logged In'}</button><button className="secondary" onClick={()=>logout.current(false)}>Logout Now</button></div></div></div>;
}
