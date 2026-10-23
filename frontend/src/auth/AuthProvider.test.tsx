// @vitest-environment jsdom
import {afterEach,it,expect,vi} from "vitest";
import {cleanup,render,screen} from "@testing-library/react";
import {MemoryRouter,Routes,Route} from "react-router-dom";
import {AuthProvider} from "./AuthProvider";
import ProtectedRoute from "./ProtectedRoute";
import {api,authApi,setAuth} from "../services/api";
afterEach(()=>{cleanup();setAuth(null);vi.restoreAllMocks()});
function app(){vi.spyOn(api,'get').mockResolvedValue({data:{id:'test',server_time:new Date().toISOString(),idle_expires_at:new Date(Date.now()+3600000).toISOString(),idle_timeout_seconds:3600,warning_seconds:300}});return <MemoryRouter initialEntries={["/projects"]}><AuthProvider><Routes><Route element={<ProtectedRoute/>}><Route path="/projects" element={<p>Private projects</p>}/></Route><Route path="/login" element={<p>Sign in first</p>}/></Routes></AuthProvider></MemoryRouter>}
it("redirects private routes when refresh fails",async()=>{vi.spyOn(authApi,"post").mockRejectedValue(new Error("No cookie"));render(app());expect(await screen.findByText("Sign in first")).toBeTruthy()});
it("restores authentication after browser reload before showing private routes",async()=>{vi.spyOn(authApi,"post").mockResolvedValue({data:{access_token:"fresh",user:{id:"u",email:"user@example.com",full_name:"User",status:"active",email_verified:true,created_at:"2026-01-01"}}});render(app());expect(screen.getByText("Restoring session…")).toBeTruthy();expect(await screen.findByText("Private projects")).toBeTruthy()});
