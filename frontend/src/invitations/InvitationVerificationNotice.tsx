import {useState} from "react";
import {useAuth} from "../auth/AuthProvider";
import {errorMessage} from "../services/api";
import {ResendVerification} from "../pages/EmailVerification";
import {useInvitations} from "./InvitationProvider";

export default function InvitationVerificationNotice(){
 const {user}=useAuth();const {refresh,loading}=useInvitations();const [message,setMessage]=useState("");const [error,setError]=useState("");
 const check=async()=>{setError("");try{await refresh();setMessage("Email status checked. Invitations appear after verification is complete.")}catch(e){setError(errorMessage(e))}};
 return <section className="invitation-verification" aria-label="Email verification required"><b>Verify your email to see invitations</b><p>Signed in as <strong>{user?.email}</strong>. Workspace invitations stay pending until this email is verified.</p><ResendVerification email={user?.email}/><div className="panel-actions"><button className="secondary" disabled={loading} onClick={()=>void check()}>{loading?"Checking…":"I have verified my email"}</button></div>{message&&<p role="status">{message}</p>}{error&&<p role="alert" className="error">{error}</p>}</section>;
}
