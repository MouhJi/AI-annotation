import {useEffect,useState} from 'react';
import {Link,NavLink,Navigate,Outlet,useLocation} from 'react-router-dom';
import {useAuth} from '../auth/AuthProvider';
import {api,errorMessage,updateAuthUser,type User} from '../services/api';
import './Admin.css';

export function AdminRouteGuard(){
 const {user,initializing}=useAuth();const [checked,setChecked]=useState(false);const [allowed,setAllowed]=useState(false);const [error,setError]=useState('');
 useEffect(()=>{let alive=true;setChecked(false);if(!user)return;void api.get<User>('/auth/me').then(({data})=>{if(alive){updateAuthUser(data);setAllowed(!!data.is_platform_admin&&data.email_verified);setChecked(true)}}).catch(e=>{if(alive){setError(errorMessage(e));setChecked(true);setAllowed(false)}});return()=>{alive=false}},[user?.id]);
 if(initializing)return <main className="editor-loading">Restoring session…</main>;
 if(!user)return <Navigate to="/login" replace state={{from:'/admin'}}/>;
 if(!checked)return <main className="editor-loading">Checking platform access…</main>;
 if(!allowed)return <main className="admin-denied"><h1>403 · Platform access required</h1><p>{error||'Workspace roles do not grant platform administrator access.'}</p><Link to="/projects">Back to app</Link></main>;
 return <Outlet/>;
}

export default function AdminLayout(){
 const {user,logout}=useAuth();const location=useLocation();const [open,setOpen]=useState(false);const [error,setError]=useState('');
 useEffect(()=>{setOpen(false)},[location.pathname]);
 return <div className="admin-shell"><aside className={`admin-sidebar ${open?'is-open':''}`}><Link className="brand" to="/admin"><span>◈</span><b>AnnotateAI</b></Link><p className="admin-sidebar-label">PLATFORM ADMINISTRATION</p><nav aria-label="Admin navigation">{[['/admin','Overview','▦'],['/admin/users','Users','♙'],['/admin/workspaces','Workspaces','◇'],['/admin/projects','Projects','▧'],['/admin/audit-logs','Audit Logs','≡'],['/admin/profile','Profile','○']].map(([to,label,icon])=><NavLink end={to==='/admin'} key={to} to={to}><span aria-hidden="true">{icon}</span>{label}</NavLink>)}</nav><Link className="admin-back" to="/projects">← Back to App</Link><small>Administrative metadata only.<br/>Private datasets keep workspace access rules.</small></aside><div className="admin-main"><header className="admin-header"><button className="secondary admin-menu" aria-label="Toggle admin navigation" aria-expanded={open} onClick={()=>setOpen(!open)}>☰</button><div><span className="eyebrow">PLATFORM</span><p>{location.pathname.split('/').filter(Boolean).map(s=>s.length>30?'Details':s.replace(/-/g,' ')).join(' / ')}</p></div><div className="admin-identity"><span className="badge">Platform Admin</span><b>{user?.full_name}</b><button className="secondary" onClick={()=>void logout().catch(e=>setError(errorMessage(e)))}>Logout</button></div></header>{error&&<p className="error" role="alert">{error}</p>}<div className="admin-page"><Outlet/></div></div></div>;
}
