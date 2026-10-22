// @vitest-environment jsdom
import {afterEach,it,expect,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter,Route,Routes,Link} from "react-router-dom";
import {CheckEmailPage,VerifyEmailPage,ResendVerification} from "./EmailVerification";
import AuthPage from "./AuthPages";
import {ProfilePage} from "./AccountPages";
import {api,authApi,type User} from "../services/api";
import * as apiService from "../services/api";
const auth=vi.hoisted(()=>({user:null as User|null,login:vi.fn()}));
vi.mock("../auth/AuthProvider",()=>({useAuth:()=>auth}));
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.useRealTimers();auth.user=null;window.history.replaceState(null,"","/");localStorage.clear()});
const renderPage=(page:React.ReactNode,entry="/verify-email#token=verification-secret-token")=>render(<MemoryRouter initialEntries={[entry]}>{page}</MemoryRouter>);

it("registration navigates to Check Email with a masked destination and actual delivery status",async()=>{
 vi.spyOn(authApi,"post").mockResolvedValue({data:{email_delivery:"sent"}});
 render(<MemoryRouter initialEntries={["/register"]}><Routes><Route path="/register" element={<AuthPage kind="register"/>}/><Route path="/check-email" element={<CheckEmailPage/>}/></Routes></MemoryRouter>);
 fireEvent.change(screen.getByLabelText("Full name"),{target:{value:"Name"}});fireEvent.change(screen.getByLabelText("Email"),{target:{value:"person@example.com"}});fireEvent.change(screen.getByLabelText("Password"),{target:{value:"strong password for testing"}});fireEvent.change(screen.getByLabelText("Confirm password"),{target:{value:"strong password for testing"}});fireEvent.click(screen.getByRole("button",{name:"Create Account"}));
 expect(await screen.findByRole("heading",{name:"Check your email"})).toBeTruthy();expect(screen.getByText(/p\*\*\*@example.com/)).toBeTruthy();expect(screen.queryByText("person@example.com")).toBeNull();expect(screen.getByRole("button",{name:/Resend available/}).hasAttribute("disabled")).toBe(true);
});
it("does not claim mail was sent when registration delivery failed",()=>{
 render(<MemoryRouter initialEntries={[{pathname:"/check-email",state:{email:"p@example.com",delivery:"failed"}}]}><CheckEmailPage/></MemoryRouter>);
 expect(screen.getByRole("status").textContent).toContain("could not send");expect(screen.getByRole("status").textContent).toContain("account is saved");
});
it("waits for confirmation before verifying and removes the fragment",async()=>{
 window.history.replaceState(null,"","/verify-email#token=verification-secret-token");const post=vi.spyOn(authApi,"post").mockResolvedValue({data:{}});renderPage(<VerifyEmailPage/>);
 expect(window.location.hash).toBe("");expect(post).not.toHaveBeenCalled();fireEvent.click(screen.getByRole("button",{name:"Verify Email"}));
 expect(await screen.findByRole("heading",{name:"Email verified"})).toBeTruthy();expect(post).toHaveBeenCalledWith("/auth/verify-email",{token:"verification-secret-token"});expect(screen.getByRole("link",{name:"Continue to Sign In"}).getAttribute("href")).toBe("/login");expect(localStorage.length).toBe(0);
});
it("accepts a newly opened email link while the verification page is already mounted",async()=>{
 const post=vi.spyOn(authApi,"post").mockResolvedValue({data:{}});
 render(<MemoryRouter initialEntries={["/verify-email"]}><VerifyEmailPage/><Link to="/verify-email#token=newly-opened-verification-token">Open newest email</Link></MemoryRouter>);
 expect(screen.queryByRole("button",{name:"Verify Email"})).toBeNull();fireEvent.click(screen.getByRole("link",{name:"Open newest email"}));fireEvent.click(await screen.findByRole("button",{name:"Verify Email"}));await waitFor(()=>expect(post).toHaveBeenCalledWith("/auth/verify-email",{token:"newly-opened-verification-token"}));
});
it("shows verification loading and prevents duplicate submission",async()=>{
 let done!:(value:unknown)=>void;const post=vi.spyOn(authApi,"post").mockImplementation(()=>new Promise(resolve=>{done=resolve}));renderPage(<VerifyEmailPage/>);fireEvent.click(screen.getByRole("button",{name:"Verify Email"}));expect(screen.getByRole("button",{name:"Verifying…"}).hasAttribute("disabled")).toBe(true);fireEvent.click(screen.getByRole("button",{name:"Verifying…"}));expect(post).toHaveBeenCalledTimes(1);await act(async()=>{done({data:{}})});
});
it.each([["Verification link has expired","Verification link expired"],["Verification link is invalid","Verification link unavailable"]])("shows safe link failure: %s",async(detail,title)=>{
 vi.spyOn(authApi,"post").mockRejectedValue({isAxiosError:true,response:{data:{detail}}});renderPage(<VerifyEmailPage/>);fireEvent.click(screen.getByRole("button",{name:"Verify Email"}));expect(await screen.findByRole("heading",{name:title})).toBeTruthy();expect(screen.getByRole("button",{name:"Resend verification email"})).toBeTruthy();
});
it("updates the current profile after verification and offers invitations",async()=>{
 auth.user={id:"u",email:"p@example.com",full_name:"Person",status:"active",email_verified:false,created_at:"2026-01-01"};const profile={...auth.user,email_verified:true};vi.spyOn(authApi,"post").mockResolvedValue({data:{}});vi.spyOn(api,"get").mockResolvedValue({data:profile});const update=vi.spyOn(apiService,"updateAuthUser");renderPage(<VerifyEmailPage/>);fireEvent.click(screen.getByRole("button",{name:"Verify Email"}));await waitFor(()=>expect(update).toHaveBeenCalledWith(profile));expect(screen.getByRole("link",{name:"View my invitations"}).getAttribute("href")).toBe("/invitations");
});
it("resend submits once and displays a cooldown",async()=>{
 const post=vi.spyOn(authApi,"post").mockResolvedValue({data:{email_delivery:"requested"}});renderPage(<ResendVerification email="p@example.com"/>);fireEvent.click(screen.getByRole("button",{name:"Resend verification email"}));await screen.findByText(/Request processed/);expect(post).toHaveBeenCalledWith("/auth/resend-verification",{email:"p@example.com"});expect(screen.getByRole("button",{name:"Resend available in 60s"}).hasAttribute("disabled")).toBe(true);
});
it("cooldown expires without sending another request",async()=>{
 vi.useFakeTimers();const post=vi.spyOn(authApi,"post");renderPage(<ResendVerification email="p@example.com" initialCooldown={2}/>);fireEvent.click(screen.getByRole("button"));expect(post).not.toHaveBeenCalled();await act(async()=>{vi.advanceTimersByTime(1000)});await act(async()=>{vi.advanceTimersByTime(1000)});expect(screen.getByRole("button",{name:"Resend verification email"}).hasAttribute("disabled")).toBe(false);
});
it("profile shows the verification badge",()=>{auth.user={id:"u",email:"p@example.com",full_name:"Person",status:"active",email_verified:true,created_at:"2026-01-01"};renderPage(<ProfilePage/>);expect(screen.getByText("Verified").className).toContain("verified-badge")});
