import {Navigate,Route,Routes} from "react-router-dom";
import {AuthProvider} from "./auth/AuthProvider";
import ProtectedRoute from "./auth/ProtectedRoute";
import AppLayout from "./components/AppLayout";
import EditorErrorBoundary from "./components/EditorErrorBoundary";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import EditorPage from "./pages/EditorPage";
import AuthPage from "./pages/AuthPages";
import {ProfilePage,SecurityPage} from "./pages/AccountPages";
import {WorkspaceProvider} from "./workspaces/WorkspaceProvider";
import WorkspaceSettingsPage from "./pages/WorkspaceSettingsPage";
import InvitationPage from "./pages/InvitationPage";
import MyInvitationsPage from "./pages/MyInvitationsPage";
import {InvitationsProvider} from "./invitations/InvitationProvider";
import {CheckEmailPage,VerifyEmailPage} from "./pages/EmailVerification";
import LandingPage from "./pages/LandingPage";
export default function App(){return <AuthProvider><Routes><Route path="/" element={<LandingPage/>}/>{(["login","register","forgot-password","reset-password"] as const).map(kind=><Route key={kind} path={`/${kind}`} element={<AuthPage key={kind} kind={kind}/>}/>)}<Route path="/check-email" element={<CheckEmailPage/>}/><Route path="/verify-email" element={<VerifyEmailPage/>}/><Route path="/invitations/accept" element={<InvitationPage/>}/><Route element={<ProtectedRoute/>}><Route element={<WorkspaceProvider/>}><Route element={<InvitationsProvider/>}><Route element={<AppLayout/>}><Route path="/projects" element={<ProjectsPage/>}/><Route path="/projects/:projectId" element={<ProjectDetailPage/>}/><Route path="/workspace/settings" element={<WorkspaceSettingsPage/>}/><Route path="/invitations" element={<MyInvitationsPage/>}/><Route path="/settings/profile" element={<ProfilePage/>}/><Route path="/settings/security" element={<SecurityPage/>}/></Route><Route path="/projects/:projectId/images/:imageId" element={<EditorErrorBoundary><EditorPage/></EditorErrorBoundary>}/></Route></Route></Route><Route path="*" element={<Navigate to="/projects" replace/>}/></Routes></AuthProvider>}
