import {useEffect,useState} from 'react';
import {Link,NavLink,Navigate,Outlet,useLocation} from 'react-router-dom';
import {useAuth} from '../auth/AuthProvider';
import {api,errorMessage,getAuthGeneration,updateAuthUser,type User} from '../services/api';
import {isPlatformAdmin} from '../auth/navigation';
import './Admin.css';

export function AdminRouteGuard(){
 const {user,initializing}=useAuth();const generation=getAuthGeneration();
 const [result,setResult]=useState<{generation:number;userId:string;allowed:boolean;error?:string}>();
 const [retry,setRetry]=useState(0);
 useEffect(()=>{
  let alive=true;
  if(initializing||!user)return;
  void api.get<User>('/auth/me').then(({data})=>{
   if(!alive||generation!==getAuthGeneration())return;
   if(data.id!==user.id)throw new Error('Session identity changed');
   updateAuthUser(data);setResult({generation,userId:user.id,allowed:isPlatformAdmin(data)});
  }).catch(e=>{if(alive&&generation===getAuthGeneration())setResult({generation,userId:user.id,allowed:false,error:errorMessage(e)})});
  return()=>{alive=false};
 },[user?.id,initializing,generation,retry]);
 if(initializing)return <main className="editor-loading">Restoring session…</main>;
 if(!user)return <Navigate to="/login" replace state={null}/>;
 if(!result||result.generation!==generation||result.userId!==user.id)return <main className="editor-loading">Checking platform access…</main>;
 if(result.error)return <main className="admin-denied"><h1>Unable to check platform access</h1><p role="alert">{result.error}</p><button onClick={()=>{setResult(undefined);setRetry(v=>v+1)}}>Retry</button><Link to="/projects">Back to app</Link></main>;
 if(!result.allowed||!isPlatformAdmin(user))return <Navigate to="/projects" replace state={null}/>;
 return <Outlet/>;
}

export default function AdminLayout(){
 const {user,logout}=useAuth();const location=useLocation();const [open,setOpen]=useState(false);const [error,setError]=useState('');
 useEffect(()=>{setOpen(false)},[location.pathname]);
 return <div className="admin-shell"><aside className={`admin-sidebar ${open?'is-open':''}`}><Link className="brand" to="/admin"><span>◈</span><b>AnnotateAI</b></Link><p className="admin-sidebar-label">PLATFORM ADMINISTRATION</p><nav aria-label="Admin navigation">{[['/admin','Overview','▦'],['/admin/users','Users','♙'],['/admin/workspaces','Workspaces','◇'],['/admin/projects','Projects','▧'],['/admin/audit-logs','Audit Logs','≡'],['/admin/profile','Profile','○']].map(([to,label,icon])=><NavLink end={to==='/admin'} key={to} to={to}><span aria-hidden="true">{icon}</span>{label}</NavLink>)}</nav><Link className="admin-back" to="/projects">← Back to App</Link><small>Administrative metadata only.<br/>Private datasets keep workspace access rules.</small></aside><div className="admin-main"><header className="admin-header"><button className="secondary admin-menu" aria-label="Toggle admin navigation" aria-expanded={open} onClick={()=>setOpen(!open)}>☰</button><div><span className="eyebrow">PLATFORM</span><p>{location.pathname.split('/').filter(Boolean).map(s=>s.length>30?'Details':s.replace(/-/g,' ')).join(' / ')}</p></div><div className="admin-identity"><span className="badge">Platform Admin</span><b>{user?.full_name}</b><button className="secondary" onClick={()=>void logout().catch(e=>setError(errorMessage(e)))}>Logout</button></div></header>{error&&<p className="error" role="alert">{error}</p>}<div className="admin-page"><Outlet/></div></div></div>;
}
