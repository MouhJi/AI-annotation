import {useEffect,useState} from "react";
import {Link,useNavigate} from "react-router-dom";
import {useAuth} from "../auth/AuthProvider";
import {api,errorMessage,updateAuthUser} from "../services/api";
import {ResendVerification} from "./EmailVerification";
export default function InvitationPage(){
 const {user,login,initializing}=useAuth();const navigate=useNavigate();const [token]=useState(()=>{const raw=new URLSearchParams(window.location.hash.slice(1)).get("token")??"";return raw});const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [message,setMessage]=useState("");
 useEffect(()=>{window.history.replaceState(null,"",window.location.pathname)},[]);
 const act=async(run:()=>Promise<void>)=>{setBusy(true);setError("");try{await run()}catch(e){setError(errorMessage(e))}finally{setBusy(false)}};
 return <main className="auth-page"><section className="auth-card"><p className="eyebrow">TEAM INVITATION</p><h1>Join a workspace</h1>
 {initializing?<p>Restoring session…</p>:!token?<p role="alert">Open the complete invitation link from your email.</p>:!user?<form className="form-stack" onSubmit={event=>{event.preventDefault();void act(()=>login(email,password))}}>
 <p>Sign in with the invited email.</p><label>Email<input type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>Password<input required type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={busy}>{busy?"Signing in…":"Sign in to join"}</button><Link to="/register" target="_blank" rel="noopener noreferrer">Create an account in another tab, then return here</Link>
 </form>:<div className="form-stack"><p>Signed in as {user.email}. Invitations can only be accepted by the matching verified email.</p>
 {!user.email_verified?<><p>Verify your email before accepting.</p><ResendVerification email={user.email}/><button className="secondary" disabled={busy} onClick={()=>void act(async()=>{updateAuthUser((await api.get("/auth/me")).data)})}>I have verified my email</button></>:<button disabled={busy} onClick={()=>void act(async()=>{const data=(await api.post("/invitations/accept",{token})).data;localStorage.setItem(`workspace:${user.id}`,data.workspace_id);navigate("/projects",{replace:true})})}>{busy?"Joining…":"Accept invitation"}</button>}</div>}
 {error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status" className="success">{message}</p>}</section></main>
}
