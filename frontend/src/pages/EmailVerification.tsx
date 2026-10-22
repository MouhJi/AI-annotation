import {useEffect,useState,type FormEvent} from "react";
import {Link,useLocation} from "react-router-dom";
import axios from "axios";
import {useAuth} from "../auth/AuthProvider";
import {api,authApi,errorMessage,updateAuthUser} from "../services/api";
import "./AuthPages.css";

export function deliveryMessage(status?:string){
 if(status==="sent")return "Your verification email was submitted for delivery. Check your inbox and spam folder.";
 if(status==="failed")return "We could not send your verification email. Your account is saved. Try again shortly or contact support.";
 if(status==="development"||status==="unavailable")return "Email delivery is not enabled on this installation. Contact the administrator to enable it, then request a new verification email.";
 if(status==="already_verified")return "Your email is already verified.";
 return "Request processed. If your account needs verification, check your inbox and spam folder. If no email arrives, retry later or contact support.";
}
export function maskEmail(email:string){const at=email.lastIndexOf("@");return at>0?`${email[0]}***${email.slice(at)}`:"your email address"}

export function ResendVerification({email:destination,initialCooldown=0}:{email?:string;initialCooldown?:number}){
 const {user}=useAuth();const [email,setEmail]=useState(destination??user?.email??"");const [cooldown,setCooldown]=useState(initialCooldown);const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [error,setError]=useState("");
 useEffect(()=>{if(!cooldown)return;const timer=window.setTimeout(()=>setCooldown(value=>Math.max(0,value-1)),1000);return()=>window.clearTimeout(timer)},[cooldown]);
 const submit=async(event:FormEvent)=>{event.preventDefault();if(busy||cooldown)return;setBusy(true);setError("");setMessage("");try{
  const own=user?.email===email;
  const data=(await (own?api.post("/auth/me/resend-verification"):authApi.post("/auth/resend-verification",{email}))).data;
  setMessage(deliveryMessage(data.email_delivery));setCooldown(60);
 }catch(e){setError(errorMessage(e));if(axios.isAxiosError(e)&&e.response?.status===429)setCooldown(Math.min(300,Math.max(60,Number(e.response.headers["retry-after"])||60)))}finally{setBusy(false)}};
 return <form className="form-stack resend-verification" onSubmit={submit}>{!destination&&!user&&<label>Email for a new verification link<input required type="email" autoComplete="email" value={email} onChange={event=>setEmail(event.target.value)}/></label>}<button className="secondary" disabled={busy||cooldown>0||!email}>{busy?"Requesting…":cooldown?`Resend available in ${cooldown}s`:"Resend verification email"}</button>{message&&<p role="status">{message}</p>}{error&&<p role="alert" className="error">{error}</p>}</form>;
}

export function CheckEmailPage(){
 const location=useLocation();const state=location.state as {email?:string;delivery?:string}|null;const email=state?.email;const delivery=state?.delivery;
 return <main className="auth-page"><section className="auth-card"><div className="email-symbol" aria-hidden="true">✉</div><h1>Check your email</h1><p>{email?`Verification for ${maskEmail(email)}.`:"Open the verification email sent to your address."}</p><p role="status" className={delivery==="failed"?"error":""}>{deliveryMessage(delivery)}</p><p>Use the Verify Email button in the message. The link expires in 24 hours. Use the newest email if you request another link.</p><ResendVerification email={email} initialCooldown={delivery==="sent"||delivery==="requested"?60:0}/><p><Link to="/login">Back to Sign In</Link></p></section></main>;
}

export function VerifyEmailPage(){
 const location=useLocation();const {user}=useAuth();const [token,setToken]=useState(()=>new URLSearchParams(location.hash.slice(1)).get("token")??"");const [state,setState]=useState<"ready"|"loading"|"success"|"error">("ready");const [error,setError]=useState("");
 useEffect(()=>{
  const incoming=new URLSearchParams(location.hash.slice(1)).get("token");
  if(incoming){setToken(incoming);setState("ready");setError("")}
  if(location.hash)window.history.replaceState(null,"",location.pathname);
 },[location.hash,location.pathname]);
 const verify=async()=>{if(!token||state==="loading")return;setState("loading");try{await authApi.post("/auth/verify-email",{token});setToken("");setState("success");if(user){try{updateAuthUser((await api.get("/auth/me")).data)}catch{/* Verification succeeded; a new sign-in can restore an expired session. */}}}catch(e){setError(errorMessage(e));setState("error")}};
 const title=state==="success"?"Email verified":state==="loading"?"Verifying your email…":state==="error"?(error.toLowerCase().includes("expired")?"Verification link expired":"Verification link unavailable"):"Verify your email";
 return <main className="auth-page"><section className="auth-card"><div className="email-symbol" aria-hidden="true">{state==="success"?"✓":"✉"}</div><h1>{title}</h1>{state==="success"?<><p role="status" className="success">Your email is verified. You can now view and accept workspace invitations.</p><Link className="button" to={user?"/invitations":"/login"}>{user?"View my invitations":"Continue to Sign In"}</Link></>:<>{state==="error"&&<p role="alert" className="error">{error}</p>}{state==="ready"&&token&&<p>Confirm below to verify the email address for this link.</p>}{state==="loading"&&<p role="status">Verifying your email…</p>}{token&&state!=="error"&&<button disabled={state==="loading"} onClick={()=>void verify()}>{state==="loading"?"Verifying…":"Verify Email"}</button>}{!token&&<p>Open the complete verification link from your email, or request a new one below.</p>}{state!=="loading"&&<ResendVerification/>}<p><Link to="/login">Back to Sign In</Link></p></>}</section></main>;
}
