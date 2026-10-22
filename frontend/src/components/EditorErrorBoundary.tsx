import {Component,ErrorInfo,ReactNode} from "react";
import "./EditorErrorBoundary.css";
type Props={children:ReactNode};type State={error:Error|null};
export default class EditorErrorBoundary extends Component<Props,State>{
 state:State={error:null};static getDerivedStateFromError(error:Error):State{return {error}}
 componentDidCatch(error:Error,info:ErrorInfo){console.error("Annotation editor failed to render",error,info)}
 render(){if(this.state.error)return <main className="editor-error"><section><p className="eyebrow">ANNOTATION EDITOR</p><h1>Unable to open this image</h1><p>The editor encountered a rendering error. Return to the project and try again after refreshing the application.</p><p className="error">Details: {this.state.error.message || "Unknown rendering error"}</p><button onClick={()=>window.history.back()}>← Back to project</button></section></main>;return this.props.children}
}
