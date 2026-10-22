import {createContext,useCallback,useContext,useEffect,useRef,useState,type ReactNode} from "react";
import {Outlet,useNavigate} from "react-router-dom";
import {api,errorMessage} from "../services/api";
import {useAuth} from "../auth/AuthProvider";

export type Workspace={id:string;name:string;slug:string;description:string|null;role:string;permissions:string[];assignable_roles:string[];project_count:number;image_count:number;annotation_count:number;member_count:number};
type Value={workspaces:Workspace[];current?:Workspace;select:(id:string)=>void;reload:()=>Promise<void>;can:(permission:string)=>boolean};
export const WorkspaceContext=createContext<Value>({workspaces:[],select:()=>{},reload:async()=>{},can:()=>false});
export const useWorkspace=()=>useContext(WorkspaceContext);

export function WorkspaceProvider({children}:{children?:ReactNode}){
 const {user}=useAuth();const navigate=useNavigate();const [workspaces,setWorkspaces]=useState<Workspace[]>([]);const [currentId,setCurrentId]=useState("");const [loading,setLoading]=useState(true);const [error,setError]=useState("");const [revision,setRevision]=useState(0);const generation=useRef(0);
 const reload=useCallback(async()=>{
  const request=++generation.current;
  try{const rows=(await api.get<Workspace[]>("/workspaces")).data;if(request!==generation.current)return;
   setWorkspaces(rows);setCurrentId(id=>rows.some(row=>row.id===id)?id:rows.some(row=>row.id===localStorage.getItem(`workspace:${user?.id}`))?localStorage.getItem(`workspace:${user?.id}`)!:rows[0]?.id??"");setError("");
  }catch(e){if(request===generation.current){setWorkspaces([]);setCurrentId("");setError(errorMessage(e));throw e}}
  finally{if(request===generation.current)setLoading(false)}
 },[user?.id]);
 useEffect(()=>{void reload().catch(()=>{});return()=>{generation.current++}},[reload]);
 useEffect(()=>{const revalidate=()=>void reload().catch(()=>{});const denied=()=>{setWorkspaces([]);setLoading(true);setRevision(v=>v+1);void reload().catch(()=>{})};window.addEventListener("focus",revalidate);window.addEventListener("workspace-access-denied",denied);const interval=window.setInterval(revalidate,15000);return()=>{window.removeEventListener("focus",revalidate);window.removeEventListener("workspace-access-denied",denied);clearInterval(interval)}},[reload]);
 const current=workspaces.find(row=>row.id===currentId);
 const select=(id:string)=>{setCurrentId(id);localStorage.setItem(`workspace:${user?.id}`,id);navigate("/projects");};
 return <WorkspaceContext.Provider value={{workspaces,current,select,reload,can:permission=>!!current?.permissions.includes(permission)}}>{loading?<main className="page">Loading workspaces…</main>:error?<main className="page"><h1>Access unavailable</h1><p role="alert">{error}</p><button onClick={()=>void reload().catch(()=>{})}>Retry</button></main>:<div key={`${currentId}:${current?.role}:${revision}`}>{children??<Outlet/>}</div>}</WorkspaceContext.Provider>
}
