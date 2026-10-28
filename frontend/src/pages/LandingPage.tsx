import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {useAuth} from '../auth/AuthProvider';
import ProductPreview from '../components/landing/ProductPreview';
import LandingIcon from '../components/landing/LandingIcon';
import './LandingPage.css';

const navigation = [
  ['Features','chuc-nang'],['Workflow','quy-trinh'],
  ['Collaboration','cong-tac'],['FAQ','hoi-dap']
];
const benefits = [
  {icon:'bounding-box' as const,tag:'Bounding box & polygon',title:'Labels that follow every object',text:'Draw bounding boxes or polygon outlines for your project. Zoom, pan and refine labels directly in the editor.'},
  {icon:'sparkle' as const,tag:'YOLO & review',title:'AI suggests. You decide.',text:'Run YOLO on selected images, then review and edit predictions before accepting them. Reject suggestions that do not fit.'},
  {icon:'users-three' as const,tag:'Workspaces & permissions',title:'Work together with clear ownership',text:'Manage members by role. Track who created and edited each annotation, and when it was last updated.'},
  {icon:'export' as const,tag:'Dataset & export',title:'Take your dataset into training',text:'Organize images and classes by project. Save your train, validation and test splits, then export your dataset in YOLO format.'}
];
const questions = [
  {id:'cau-hoi-loai-nhan',question:'Which annotation types are supported?',answer:'Create an object detection project for bounding boxes or an instance segmentation project for polygons. Each object is assigned to a class defined in the project.'},
  {id:'cau-hoi-ai',question:'Can I edit predictions suggested by YOLO?',answer:'Yes. Change classes and adjust prediction coordinates before accepting, or reject a prediction. Accepted annotations can also be edited directly if your account has permission. AI labeling requires a YOLO model configured on the server.'},
  {id:'cau-hoi-editor',question:'How do I refine labels on large images?',answer:'Use the plus and minus buttons or the mouse wheel to zoom around your cursor. Hold Space and drag with the left mouse button to pan. Move and resize bounding boxes, or drag individual polygon vertices. Fit to screen shows the whole image; 100% maps one image pixel to one CSS pixel.'},
  {id:'cau-hoi-vai-tro',question:'Do all workspace members have the same permissions?',answer:'No. The available roles are Owner, Admin, Annotator, Reviewer and Viewer. Actions depend on workspace roles and annotation permissions. Viewers can only view data. Workspace administration and platform administration are separate permissions.'},
  {id:'cau-hoi-export',question:'How are datasets exported?',answer:'Download a YOLO ZIP for bounding boxes or polygons. It contains images, labels and data.yaml. Train, validation and test assignments are saved for consistent exports.'},
  {id:'cau-hoi-split',question:'Can I change the dataset split ratios?',answer:'Yes. Enter your train, validation and test ratios in Dataset Export, then save the split. The defaults are 80%, 10% and 10%, and the total must equal 100%. Each image belongs to one split. Images without objects are included too.'},
  {id:'quyen-rieng-tu',question:'How is my data managed?',answer:'Images, classes and annotations belong to projects within a workspace. The API checks access permissions for data operations, and authentication uses sessions and cookies. This landing page shows sample data only and does not load your private datasets. Ask your deployment administrator about applicable retention, backup and privacy policies.'},
  {id:'dieu-kien-su-dung',question:'How do I get started?',answer:'Select “Start annotating” to create an account, then sign in to work in your workspace. If you are already signed in, this button opens your workspace. Email verification and invitation delivery depend on server configuration. Your deployment administrator provides the terms that apply to your installation.'}
];
function Brand(){return <Link className="lp-brand" to="/" aria-label="AnnotateAI, home" aria-current="page"><img src="/favicon.svg" width="32" height="32" alt=""/>Annotate<span>AI</span></Link>;}
function Action({destination,small=false}:{destination:string;small?:boolean}){
  return <Link className={'lp-action'+(small?' lp-action-small':'')} to={destination}>Start annotating<LandingIcon name="arrow-up-right"/></Link>;
}

function LandingNavbar({destination,signedIn,active}:{destination:string;signedIn:boolean;active:string}){
  const [open,setOpen]=useState(false);
  const toggle=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null);
  const close=()=>{setOpen(false);toggle.current?.focus();};
  useEffect(()=>{
    const wide=window.matchMedia?.('(min-width: 901px)');
    const changed=()=>{if(wide?.matches)setOpen(false);};
    wide?.addEventListener?.('change',changed);
    return()=>wide?.removeEventListener?.('change',changed);
  },[]);
  useEffect(()=>{
    if(!open)return;
    const before=document.body.style.overflow;
    document.body.style.overflow='hidden';
    panel.current?.querySelector<HTMLAnchorElement>('nav a')?.focus();
    return()=>{document.body.style.overflow=before;};
  },[open]);
  const menuLinks=navigation.map(([label,id],index)=><a href={'#'+id} key={id} aria-current={active===id?'location':undefined} style={{animationDelay:index*60+'ms'}} onClick={()=>setOpen(false)}>{label}</a>);
  return <header className="lp-nav">
    <div className="lp-nav-inner"><Brand/>
      <nav className="lp-desktop-nav" aria-label="Main navigation">{menuLinks}</nav>
      <div className="lp-nav-actions">{!signedIn&&<Link className="lp-login" to="/login">Log in</Link>}<Action destination={destination} small/></div>
      <button ref={toggle} className={'lp-menu-toggle'+(open?' is-open':'')} aria-label="Open menu" aria-expanded={open} aria-controls="landing-mobile-nav" tabIndex={open?-1:0} onClick={()=>setOpen(true)}><span/><span/></button>
    </div>
    {open&&<div ref={panel} id="landing-mobile-nav" className="lp-mobile-panel" role="dialog" aria-modal="true" aria-label="Navigation menu" onKeyDown={event=>{
      if(event.key==='Escape'){event.preventDefault();close();}
      if(event.key==='Tab'){
        const elements=panel.current!.querySelectorAll<HTMLElement>('a,button'),first=elements[0],last=elements[elements.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    }}>
      <div className="lp-mobile-head"><Brand/><button className="lp-menu-toggle is-open" aria-label="Close menu" onClick={close}><span/><span/></button></div>
      <nav aria-label="Mobile navigation">{menuLinks}{!signedIn&&<Link to="/login" style={{animationDelay:'240ms'}}>Log in</Link>}<Action destination={destination}/></nav>
      <p>Label images. Review results. Prepare datasets.</p>
    </div>}
  </header>;
}

function EditorScreenshot(){
  const [state,setState]=useState<'loading'|'loaded'|'error'>('loading');
  return <figure className="lp-product-shot" data-reveal>
    <div className="lp-shot-heading"><span><span className="lp-status-dot"/>AnnotateAI <span aria-hidden="true">/</span> Image annotation editor</span><span className="lp-shot-badge">Product screenshot</span></div>
    <div className="lp-shot-body" aria-busy={state==='loading'}>
      {state==='loading'&&<div className="lp-shot-skeleton" role="status"><span className="lp-sr-only">Loading editor screenshot…</span><i/><i/><i/></div>}
      {state!=='error'?<img className={state==='loaded'?'is-loaded':''} src="/landing/annotation-editor.png" width="1280" height="720" alt="AnnotateAI editor with classes, bounding boxes and polygons on a sample image, and an object list on the right" loading="eager" decoding="async" onLoad={()=>setState('loaded')} onError={()=>setState('error')}/>:<div className="lp-shot-error" role="status"><strong>Could not load the editor screenshot</strong><p>You can still explore the features and workflow below.</p><a href="#chuc-nang">Explore the features <span aria-hidden="true">↓</span></a></div>}
    </div>
    <figcaption><span>The actual editor with sample data in Viewer mode.</span><span>Bounding box · Polygon · Classes</span></figcaption>
  </figure>;
}
function GeometryIllustration(){return <svg className="lp-geometry-illustration" viewBox="0 0 480 200" aria-hidden="true">
  <rect x="32" y="24" width="416" height="152" rx="12" fill="#fff"/>
  <path d="M72 150 100 72 164 64 192 128 146 158Z" fill="#bae6fd"/>
  <rect x="80" y="48" width="140" height="112" rx="4" fill="none" stroke="#0284c7" strokeWidth="2"/>
  <path d="m282 136 14-64 62-24 58 48-40 60Z" fill="#e0f2fe" stroke="#0284c7" strokeWidth="2"/>
  {[[80,48],[220,48],[80,160],[220,160],[282,136],[296,72],[358,48],[416,96],[376,156]].map(([x,y],i)=><rect key={i} x={x-4} y={y-4} width="8" height="8" rx="2" fill="white" stroke="#0284c7" strokeWidth="2"/>)}
  <text x="88" y="40" fontSize="12" fontFamily="inherit" fill="#0369a1">Bounding box</text><text x="296" y="32" fontSize="12" fontFamily="inherit" fill="#0369a1">Polygon</text>
</svg>;}
function FeaturesSection(){return <section id="chuc-nang" className="lp-section lp-features" aria-labelledby="lp-features-heading">
  <div className="lp-container"><div className="lp-section-intro" data-reveal><p className="lp-eyebrow">From drawing to datasets</p><h2 id="lp-features-heading">Refine every label.<br/>Connect your workflow.</h2><p>Tools for you and your team, from the first image to the final export.</p></div>
    <div className="lp-feature-grid">{benefits.map((item,index)=><article className={'lp-feature-card lp-feature-card-'+index} key={item.title} data-reveal><div className="lp-feature-icon"><LandingIcon name={item.icon}/></div><div className="lp-feature-copy"><span className="lp-feature-category">{item.tag}</span><h3>{item.title}</h3><p>{item.text}</p></div>{index===0&&<GeometryIllustration/>}</article>)}</div>
  </div>
</section>;}
function ProductProof(){return <section className="lp-section lp-proof" aria-labelledby="lp-proof-heading"><div className="lp-container lp-proof-layout">
  <div className="lp-proof-copy" data-reveal><p className="lp-eyebrow">Inside the app</p><h2 id="lp-proof-heading">Every label,<br/>in context.</h2><p>View images, classes and objects together in the editor. Select a label to review and edit it directly with the permissions assigned to you.</p><ul><li><LandingIcon name="check"/>Bounding boxes and polygons for each project mode.</li><li><LandingIcon name="check"/>Creator and editor attribution on annotations.</li><li><LandingIcon name="check"/>Zoom, pan and edit in original image coordinates.</li></ul><span className="lp-proof-note">The screenshot shows the actual interface in Viewer mode with sample data.</span></div>
  <EditorScreenshot/>
</div></section>;}
function Tagline(){
  const lines=['AI can suggest.','You control every label.'];
  let index=0;
  return <section className="lp-tagline-section" aria-labelledby="lp-tagline"><div className="lp-container">
    <p className="lp-eyebrow">Keep people in control</p>
    <h2 id="lp-tagline" aria-label={lines.join(' ')}>{lines.map(line=><span className="lp-tagline-line" aria-hidden="true" key={line}>{line.split(' ').map(word=><span data-word key={index} style={{transitionDelay:index++*45+'ms'}}>{word}{' '}</span>)}</span>)}</h2>
    <p>Review results, refine shapes and choose the right classes before adding labels to your dataset.</p>
  </div></section>;
}
function WorkflowSection(){return <section id="quy-trinh" className="lp-section lp-workflow" aria-labelledby="lp-workflow-heading"><div className="lp-container">
  <div className="lp-section-intro" data-reveal><p className="lp-eyebrow">Your workflow</p><h2 id="lp-workflow-heading">From your first project<br/>to your final export.</h2></div>
  <ol className="lp-steps">{[
    ['Prepare images and classes','Create a project in your workspace, choose bounding boxes or polygons, upload images and add your classes.'],
    ['Annotate, review and refine','Draw manually or run YOLO for suggestions. Review, accept and refine annotations with your assigned permissions.'],
    ['Save splits and export','Set your train, validation and test ratios. Save image assignments, then download a YOLO ZIP for training.']
  ].map(([title,text],index)=><li data-reveal key={title}><span className="lp-step-number">0{index+1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol>
  <div className="lp-export-panel" data-reveal><div><p className="lp-eyebrow">Split once, export consistently</p><h3>Every image keeps its split.</h3><p>Adjust ratios in your project and export again using the saved assignments.</p></div><div className="lp-split-example" aria-label="Default dataset split ratios, adjustable in your project"><div className="lp-split-bar" aria-hidden="true"><span/><span/><span/></div><dl><div><dt>Train</dt><dd>80%</dd></div><div><dt>Validation</dt><dd>10%</dd></div><div><dt>Test</dt><dd>10%</dd></div></dl><p>Default ratios. Adjust them in Dataset Export.</p></div></div>
</div></section>;}
const workspaceRoles=[
  {id:'owner',name:'Owner',label:'Workspace owner',description:'Manage the workspace, members and projects, including actions reserved for the workspace owner.'},
  {id:'admin',name:'Admin',label:'Workspace administrator',description:'Manage projects, images, classes and members within your assigned permissions.'},
  {id:'annotator',name:'Annotator',label:'Annotator',description:'Create and edit annotations, run YOLO and review suggestions according to object permissions.'},
  {id:'reviewer',name:'Reviewer',label:'Reviewer',description:'Review and edit annotations, and approve YOLO suggestions according to workspace permissions.'},
  {id:'viewer',name:'Viewer',label:'Viewer',description:'View projects, images and annotations. Cannot create, edit or delete labels.'}
];
function CollaborationSection(){
  const [selected,setSelected]=useState(2),tabs=useRef<(HTMLButtonElement|null)[]>([]);
  const role=workspaceRoles[selected];
  return <section id="cong-tac" className="lp-section lp-collaboration" aria-labelledby="lp-collab-heading"><div className="lp-container lp-collab-layout">
    <div className="lp-collab-copy" data-reveal><p className="lp-eyebrow">Shared work, clear ownership</p><h2 id="lp-collab-heading">One team effort.<br/>Every contribution visible.</h2><p>Invite members to your workspace and assign roles for their work. Annotations retain creator, editor and update information.</p><div className="lp-attribution-example"><LandingIcon name="users-three"/><span><b>From annotators to reviewers</b><small>One workspace. One shared dataset.</small></span></div></div>
    <div className="lp-role-panel" data-reveal><div className="lp-role-heading"><span><LandingIcon name="users-three"/>Workspace roles</span><span className="lp-role-note">Select a role to explore</span></div><div className="lp-role-tabs" role="tablist" aria-label="Workspace role preview">{workspaceRoles.map((item,index)=><button ref={node=>{tabs.current[index]=node;}} key={item.id} id={'role-tab-'+item.id} type="button" role="tab" aria-selected={selected===index} aria-controls={'role-panel-'+role.id} tabIndex={selected===index?0:-1} onClick={()=>setSelected(index)} onKeyDown={event=>{
      let next=index;
      if(event.key==='ArrowRight')next=(index+1)%workspaceRoles.length;else if(event.key==='ArrowLeft')next=(index+workspaceRoles.length-1)%workspaceRoles.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=workspaceRoles.length-1;else return;
      event.preventDefault();setSelected(next);tabs.current[next]?.focus();
    }}>{item.name}</button>)}</div><div className="lp-role-description" key={role.id} id={'role-panel-'+role.id} role="tabpanel" tabIndex={0} aria-labelledby={'role-tab-'+role.id}><span className="lp-role-symbol"><LandingIcon name={role.id==='viewer'?'cursor':'check'}/></span><h3>{role.label}</h3><p>{role.description}</p></div><p className="lp-role-footnote">This is a permissions preview. Workspace administration and platform administration are separate.</p></div>
  </div></section>;
}
function FAQSection(){return <section id="hoi-dap" className="lp-section lp-faq" aria-labelledby="lp-faq-heading"><div className="lp-container lp-faq-layout"><div className="lp-section-intro" data-reveal><p className="lp-eyebrow">Before you begin</p><h2 id="lp-faq-heading">A few things<br/>you might ask.</h2><p>Features, access permissions and how your data is used.</p></div><div className="lp-faq-list" data-reveal>{questions.map(item=><details key={item.id} id={item.id}><summary>{item.question}<span aria-hidden="true">+</span></summary><p>{item.answer}</p></details>)}</div></div></section>;}

export default function LandingPage(){
  const {user,initializing}=useAuth();
  // Keep the existing landing destinations; login routing remains in authentication.
  const destination=user?'/projects':'/register';
  const root=useRef<HTMLDivElement>(null),[active,setActive]=useState('');
  useEffect(()=>{
    const oldTitle=document.title,oldLang=document.documentElement.lang;
    document.title='AnnotateAI | Image annotation and YOLO datasets';
    document.documentElement.lang='en';
    return()=>{document.title=oldTitle;document.documentElement.lang=oldLang;};
  },[]);
  useEffect(()=>{
    const element=root.current!;
    if(typeof IntersectionObserver==='undefined')return;
    const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const sections=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting)setActive(entry.target.id==='gioi-thieu'?'':entry.target.id);},{rootMargin:'-15% 0px -65% 0px',threshold:0});
    for(const id of ['gioi-thieu',...navigation.map(([,id])=>id)]){const section=element.querySelector('#'+id);if(section)sections.observe(section);}
    if(reduced)return()=>sections.disconnect();
    element.dataset.motion='ready';
    const reveal=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){entry.target.classList.add('is-visible');reveal.unobserve(entry.target);}},{threshold:0.12});
    element.querySelectorAll('[data-reveal]').forEach(node=>reveal.observe(node));
    const words=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){entry.target.classList.add('is-active');words.unobserve(entry.target);}},{rootMargin:'0px 0px -20% 0px',threshold:1});
    element.querySelectorAll('[data-word]').forEach(node=>words.observe(node));
    return()=>{sections.disconnect();reveal.disconnect();words.disconnect();delete element.dataset.motion;};
  },[]);
  const openDisclosure=(id:string)=>{const details=document.getElementById(id) as HTMLDetailsElement|null;if(details)details.open=true;};
  const schema={'@context':'https://schema.org','@type':'FAQPage',mainEntity:questions.map(item=>({'@type':'Question',name:item.question,acceptedAnswer:{'@type':'Answer',text:item.answer}}))};
  return <div className="lp-root" ref={root}>
    <a className="lp-skip" href="#main-content">Skip to main content</a>
    <LandingNavbar destination={destination} signedIn={!!user} active={active}/>
    <main id="main-content" tabIndex={-1}>
      <section id="gioi-thieu" className="lp-hero" aria-labelledby="lp-title"><div className="lp-container">
        <div className="lp-hero-copy"><p className="lp-eyebrow"><LandingIcon name="sparkle"/>A workspace for computer vision teams</p><h1 id="lp-title">Better training data.<br/>One label at a time.</h1><p>Draw bounding boxes, trace polygons and review YOLO suggestions. From raw images to a labeled dataset, in one workspace.</p><div className="lp-hero-action">{initializing?<span className="lp-action-skeleton" role="status">Checking your session…</span>:<Action destination={destination}/>}<span>{user?'Continue working in your workspace.':'Create an account to start in your workspace.'}</span></div></div>
        <div className="lp-demo-stage" data-reveal><div className="lp-demo-frame"><ProductPreview/></div><div className="lp-stage-note lp-stage-note-top" aria-hidden="true"><span className="lp-stage-note-icon"><LandingIcon name="polygon"/></span><span><b>Every outline matters</b><small>Bounding box · Polygon</small></span></div><div className="lp-stage-note lp-stage-note-bottom" aria-hidden="true"><span className="lp-stage-note-icon"><LandingIcon name="export"/></span><span><b>From images to datasets</b><small>Export labels in YOLO format</small></span></div></div>
        <p className="lp-demo-caption"><span/>Select an object or switch annotation types in the preview above.</p>
      </div></section>
      <FeaturesSection/><Tagline/><WorkflowSection/><ProductProof/><CollaborationSection/><FAQSection/>
      <section className="lp-section lp-final" aria-labelledby="lp-final-heading"><div className="lp-container" data-reveal><p className="lp-eyebrow">Start with your project</p><h2 id="lp-final-heading">Bring your images.<br/>Start shaping your dataset.</h2><p>Create a project, define your classes and prepare your dataset for what comes next.</p><Action destination={destination}/><span>{user?'Open your workspace to continue.':'You will be taken to account registration.'}</span></div></section>
    </main>
    <footer className="lp-footer"><div className="lp-container"><div className="lp-footer-top"><div><Brand/><p>An image annotation workspace<br/>for computer vision teams.</p></div><nav aria-label="Footer navigation"><a href="#chuc-nang">Features</a><a href="#quy-trinh">Workflow</a><a href="#hoi-dap">FAQ</a><Link to="/login">Log in</Link></nav></div><div className="lp-footer-bottom"><span>© {new Date().getFullYear()} AnnotateAI</span><div><a href="#quyen-rieng-tu" onClick={()=>openDisclosure('quyen-rieng-tu')}>Privacy</a><a href="#dieu-kien-su-dung" onClick={()=>openDisclosure('dieu-kien-su-dung')}>Terms of use</a><a href="#main-content">Back to top ↑</a></div></div></div></footer>
    <script type="application/ld+json">{JSON.stringify(schema)}</script>
  </div>;
}
