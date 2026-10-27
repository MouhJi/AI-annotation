// @vitest-environment jsdom
import {useEffect,useState} from 'react';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MemoryRouter,Route,Routes,useLocation,useNavigate,useNavigationType} from 'react-router-dom';
import {AxiosError,type AxiosResponse,type InternalAxiosRequestConfig} from 'axios';
import {AuthProvider,useAuth} from './AuthProvider';
import ProtectedRoute from './ProtectedRoute';
import {AdminRouteGuard} from '../admin/AdminLayout';
import {WorkspaceProvider,useWorkspace} from '../workspaces/WorkspaceProvider';
import AuthPage from '../pages/AuthPages';
import {api,authApi,setAuth,type User} from '../services/api';
import {loginDestination} from './navigation';

const admin:User={id:'admin',email:'admin@example.com',full_name:'Platform admin',is_platform_admin:true,email_verified:true,status:'active',created_at:'2026-01-01'};
const member:User={...admin,id:'member',email:'member@example.com',full_name:'Workspace admin',is_platform_admin:false};
let cookie:User|null,privateRequests:string[];
const originalAPI=api.defaults.adapter,originalAuth=authApi.defaults.adapter;
const response=(config:InternalAxiosRequestConfig,data:unknown):AxiosResponse=>({config,data,status:200,statusText:'OK',headers:{}});
const policy=(user:User)=>({id:'session:'+user.id,server_time:new Date().toISOString(),idle_expires_at:new Date(Date.now()+3600000).toISOString(),idle_timeout_seconds:3600,warning_seconds:300});
const authResult=(user:User)=>({access_token:'token:'+user.id,user,session:policy(user)});
const unauthorized=(config:InternalAxiosRequestConfig)=>new AxiosError('No session','401',config,undefined,{...response(config,{}),status:401});
beforeEach(()=>{
  cookie=null;privateRequests=[];localStorage.clear();sessionStorage.clear();setAuth(null);
  authApi.defaults.adapter=async config=>{
    if(config.url==='/auth/login'){const data=JSON.parse(config.data);cookie=data.email===admin.email?admin:member;return response(config,authResult(cookie));}
    if(config.url==='/auth/refresh'){if(!cookie)throw unauthorized(config);return response(config,authResult(cookie));}
    if(config.url?.startsWith('/auth/logout')){cookie=null;return response(config,{});}
    throw new Error('Unexpected auth URL '+config.url);
  };
  api.defaults.adapter=async config=>{
    const user=config.headers.Authorization==='Bearer token:admin'?admin:config.headers.Authorization==='Bearer token:member'?member:null;
    if(!user)throw unauthorized(config);
    if(config.url==='/auth/me')return response(config,user);
    if(config.url==='/auth/session')return response(config,policy(user));
    if(config.url==='/workspaces')return response(config,[{id:'workspace:'+user.id,name:'Workspace for '+user.full_name,role:'admin',permissions:[],assignable_roles:[]}]);
    if(config.url==='/admin/fixture'){privateRequests.push(user.id);return response(config,{name:'Admin data for '+user.full_name});}
    throw new Error('Unexpected API URL '+config.url);
  };
});
afterEach(()=>{cleanup();setAuth(null);api.defaults.adapter=originalAPI;authApi.defaults.adapter=originalAuth;vi.restoreAllMocks();});

function Probe(){const location=useLocation(),navigate=useNavigate(),kind=useNavigationType();return <><output aria-label='Route'>{location.pathname}</output><output aria-label='Route state'>{JSON.stringify(location.state)}</output><output aria-label='Navigation type'>{kind}</output><button onClick={()=>navigate(-1)}>History back</button><button onClick={()=>navigate('/admin/users/42')}>Go admin child</button></>;}
function Logout(){const {user,logout}=useAuth();return <><p>Account: {user?.id}</p><button onClick={()=>void logout().catch(()=>{})}>Logout fixture</button></>;}
function AdminPage(){const [data,setData]=useState('');useEffect(()=>{let alive=true;void api.get('/admin/fixture').then(r=>{if(alive)setData(r.data.name)}).catch(()=>{});return()=>{alive=false};},[]);return <><h1>Private administration</h1><p>{data}</p><Logout/></>;}
function WorkspacePage(){const {current}=useWorkspace();return <><h1>Workspace home</h1><p>{current?.name}</p><input aria-label='Selected images' defaultValue=''/><Logout/></>;}
function show(entries:any[]=['/login']){return render(<MemoryRouter initialEntries={entries}><AuthProvider><Probe/><Routes>
  <Route path='/before' element={<p>Public before</p>}/><Route path='/login' element={<AuthPage kind='login'/>}/>
  <Route element={<ProtectedRoute/>}>
    <Route element={<AdminRouteGuard/>}><Route path='/admin/*' element={<AdminPage/>}/></Route>
    <Route element={<WorkspaceProvider/>}><Route path='/projects/*' element={<WorkspacePage/>}/></Route>
  </Route>
</Routes></AuthProvider></MemoryRouter>);}
async function login(user:User){await screen.findByRole('button',{name:'Sign In'});fireEvent.change(screen.getByLabelText('Email'),{target:{value:user.email}});fireEvent.change(screen.getByLabelText('Password'),{target:{value:'Fixture password'}});fireEvent.click(screen.getByRole('button',{name:'Sign In'}));}
const route=()=>screen.getByLabelText('Route').textContent;

it('admin → logout → member goes to workspace, clearing redirects and protecting older admin history entries',async()=>{
  cookie=admin;show(['/admin/users','/projects','/admin']);
  await screen.findByText('Admin data for Platform admin');
  localStorage.setItem('returnTo','/admin');sessionStorage.setItem('redirectTo','/admin/users');localStorage.setItem('workspace:admin','old-private-workspace');
  fireEvent.click(screen.getByRole('button',{name:'Logout fixture'}));await screen.findByRole('button',{name:'Sign In'});
  expect(route()).toBe('/login');expect(screen.getByLabelText('Route state').textContent).toBe('null');expect(screen.getByLabelText('Navigation type').textContent).toBe('REPLACE');
  expect(screen.queryByText('Private administration')).toBeNull();expect(localStorage.getItem('workspace:admin')).toBeNull();
  await login(member);await screen.findByText('Workspace for Workspace admin');
  expect(route()).toBe('/projects');expect(screen.getByLabelText('Navigation type').textContent).toBe('REPLACE');
  fireEvent.click(screen.getByRole('button',{name:'History back'}));await waitFor(()=>expect(route()).toBe('/projects'));
  fireEvent.click(screen.getByRole('button',{name:'History back'}));await waitFor(()=>expect(screen.getByLabelText('Navigation type').textContent).toBe('REPLACE'));
  await screen.findByText('Workspace for Workspace admin');expect(route()).toBe('/projects');expect(screen.queryByText('Private administration')).toBeNull();expect(privateRequests).toEqual(['admin']);
});
it('member → logout → admin goes to /admin and drops the previous workspace selection',async()=>{
  cookie=member;show(['/projects']);await screen.findByText('Workspace for Workspace admin');
  fireEvent.change(screen.getByLabelText('Selected images'),{target:{value:'old private image IDs'}});
  fireEvent.click(screen.getByRole('button',{name:'Logout fixture'}));await login(admin);
  await screen.findByText('Admin data for Platform admin');expect(route()).toBe('/admin');expect(screen.queryByDisplayValue('old private image IDs')).toBeNull();
});
for(const path of ['/admin','/admin/users','/admin/users/42'])it(`redirects a regular workspace admin away from ${path} with replace`,async()=>{
  cookie=member;show([path]);await screen.findByText('Workspace for Workspace admin');expect(route()).toBe('/projects');expect(screen.getByLabelText('Navigation type').textContent).toBe('REPLACE');expect(privateRequests).toEqual([]);
});
for(const user of [admin,member])it(`unauthenticated admin deep link signs in as ${user.id} using the new account's platform flag`,async()=>{
  show([{pathname:'/admin/users/42',state:{from:'/admin',returnTo:'/admin',redirectTo:'/admin'}}]);
  await screen.findByRole('button',{name:'Sign In'});expect(route()).toBe('/login');expect(screen.getByLabelText('Route state').textContent).toBe('null');
  await login(user);await screen.findByRole('heading',{name:user===admin?'Private administration':'Workspace home'});expect(route()).toBe(user===admin?'/admin':'/projects');
});
for(const user of [admin,member])it(`ignores stale login location/storage redirects for ${user.id}`,async()=>{
  localStorage.setItem('returnTo','/admin');sessionStorage.setItem('redirectTo','/projects/old-private-project');
  show([{pathname:'/login',state:{from:user===admin?'/projects/old':'/admin/users',redirectTo:'/admin'}}]);
  await login(user);await screen.findByRole('heading',{name:user===admin?'Private administration':'Workspace home'});expect(route()).toBe(user===admin?'/admin':'/projects');expect(screen.getByLabelText('Route state').textContent).toBe('null');
});
for(const [user,path] of [[admin,'/admin/users/42'],[member,'/projects/22']] as const)it(`restores ${user.id} after refresh and preserves the permitted URL ${path}`,async()=>{
  cookie=user;let finish!:(value:AxiosResponse)=>void;
  authApi.defaults.adapter=config=>new Promise(resolve=>{finish=data=>resolve(response(config,data.data));});
  show([path]);expect(screen.getByText('Restoring session…')).toBeTruthy();expect(route()).toBe(path);expect(screen.queryByRole('button',{name:'Sign In'})).toBeNull();expect(screen.queryByText('Private administration')).toBeNull();
  await waitFor(()=>expect(finish).toBeTypeOf('function'));await act(async()=>{finish({data:authResult(user)} as AxiosResponse);});
  await screen.findByRole('heading',{name:user===admin?'Private administration':'Workspace home'});expect(route()).toBe(path);
});
it('keeps admin pages hidden until the live profile check completes',async()=>{
  cookie=admin;const adapter=api.defaults.adapter as (config:InternalAxiosRequestConfig)=>Promise<AxiosResponse>;
  let resolveProfile!:(data:AxiosResponse)=>void;
  api.defaults.adapter=config=>config.url==='/auth/me'?new Promise(resolve=>{resolveProfile=data=>resolve(response(config,data.data));}):adapter(config);
  show(['/admin/users']);await screen.findByText('Checking platform access…');expect(screen.queryByText('Private administration')).toBeNull();expect(privateRequests).toEqual([]);
  await act(async()=>resolveProfile({data:admin} as AxiosResponse));await screen.findByText('Admin data for Platform admin');expect(route()).toBe('/admin/users');
});
it('uses only active verified platform flags, independently of workspace roles',()=>{
  expect(loginDestination({...member,is_platform_admin:false})).toBe('/projects');
  expect(loginDestination({...admin,email_verified:false})).toBe('/projects');
  expect(loginDestination({...admin,status:'disabled'})).toBe('/projects');
  expect(loginDestination(admin)).toBe('/admin');
});
