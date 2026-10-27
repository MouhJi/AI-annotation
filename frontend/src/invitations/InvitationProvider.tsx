import {createContext,useCallback,useContext,useEffect,useRef,useState,type ReactNode} from "react";
import {Outlet} from "react-router-dom";
import {useAuth} from "../auth/AuthProvider";
import {api,errorMessage,updateAuthUser,type User} from "../services/api";
import {useWorkspace} from "../workspaces/WorkspaceProvider";

export type MyInvitation={invitation_id:string;workspace_id:string;workspace_name:string;invited_role:string;invited_by_name:string;created_at:string;expires_at:string;status:"pending"};
type Value={invitations:MyInvitation[];loading:boolean;error:string;verificationRequired:boolean;refresh:()=>Promise<void>;accept:(id:string)=>Promise<{workspace_id:string}>;decline:(id:string)=>Promise<void>};
const InvitationContext=createContext<Value>({invitations:[],loading:false,error:"",verificationRequired:false,refresh:async()=>{},accept:async()=>({workspace_id:""}),decline:async()=>{}});
export const useInvitations=()=>useContext(InvitationContext);

export function InvitationsProvider({children}:{children?:ReactNode}){
 const {user}=useAuth();const {reload}=useWorkspace();const [invitations,setInvitations]=useState<MyInvitation[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState("");
 const generation=useRef(0);
 const refresh=useCallback(async()=>{
  const request=++generation.current;
  if(!user){setInvitations([]);setLoading(false);return}
  setLoading(true);try{
   // Verification may have completed in another tab. Recheck the authenticated
   // profile before querying invitations, whose API requires verified email.
   if(!user.email_verified){const profile=(await api.get<User>("/auth/me")).data;if(request!==generation.current)return;if(!profile.email_verified){setInvitations([]);setError("");return}updateAuthUser(profile)}
   const rows=(await api.get<MyInvitation[]>("/me/invitations")).data;
   if(request!==generation.current)return;setInvitations(rows);setError("")
  }catch(e){if(request===generation.current)setError(errorMessage(e));throw e}finally{if(request===generation.current)setLoading(false)}
 },[user?.id,user?.email_verified]);
 useEffect(()=>{setInvitations([]);setError("");void refresh().catch(()=>{});const onFocus=()=>void refresh().catch(()=>{});window.addEventListener("focus",onFocus);const timer=window.setInterval(onFocus,30000);return()=>{generation.current++;window.removeEventListener("focus",onFocus);window.clearInterval(timer)}},[refresh]);
 const accept=async(id:string)=>{const result=(await api.post<{workspace_id:string}>(`/me/invitations/${id}/accept`)).data;await Promise.all([refresh(),reload()]);return result};
 const decline=async(id:string)=>{await api.post(`/me/invitations/${id}/decline`);await refresh()};
 return <InvitationContext.Provider value={{invitations,loading,error,verificationRequired:!!user&&!user.email_verified,refresh,accept,decline}}>{children??<Outlet/>}</InvitationContext.Provider>;
}
