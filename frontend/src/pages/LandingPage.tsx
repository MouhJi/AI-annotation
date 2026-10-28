import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {useAuth} from '../auth/AuthProvider';
import './LandingPage.css';

const navigation = [
  ['Tính năng','chuc-nang'],['Quy trình','quy-trinh'],
  ['Cộng tác','cong-tac'],['Hỏi đáp','hoi-dap']
];
const benefits = [
  {tag:'Bounding box & polygon',title:'Nhãn bám sát từng đối tượng',text:'Vẽ khung bao hoặc đường viền polygon theo chế độ của project. Phóng to, di chuyển ảnh và chỉnh lại nhãn ngay trong editor.'},
  {tag:'YOLO & kiểm tra kết quả',title:'AI gợi ý, bạn quyết định',text:'Chạy YOLO cho ảnh đã chọn, xem và sửa dự đoán trước khi chấp nhận. Bạn cũng có thể từ chối gợi ý chưa phù hợp.'},
  {tag:'Workspace & phân quyền',title:'Làm chung, rõ trách nhiệm',text:'Quản lý thành viên theo vai trò. Theo dõi người tạo, người chỉnh sửa và thời điểm cập nhật của từng annotation.'},
  {tag:'Dataset & export',title:'Mang dữ liệu sang bước huấn luyện',text:'Quản lý ảnh và lớp nhãn theo project. Lưu cách chia train, validation, test rồi tải dataset theo định dạng YOLO.'}
];
const questions = [
  {id:'cau-hoi-loai-nhan',question:'Hệ thống hỗ trợ những kiểu gán nhãn nào?',answer:'Bạn có thể tạo project phát hiện đối tượng để vẽ bounding box, hoặc project phân đoạn instance để vẽ polygon. Mỗi đối tượng được gắn với một lớp nhãn của project.'},
  {id:'cau-hoi-ai',question:'Tôi có thể sửa kết quả do YOLO đề xuất không?',answer:'Có. Bạn có thể đổi lớp nhãn và chỉnh tọa độ dự đoán trước khi chấp nhận, hoặc từ chối dự đoán. Annotation đã chấp nhận cũng có thể được chỉnh trực tiếp nếu tài khoản có quyền. Chức năng AI cần model YOLO được cấu hình trên máy chủ.'},
  {id:'cau-hoi-editor',question:'Làm thế nào để chỉnh chi tiết trên ảnh lớn?',answer:'Trong editor, dùng nút cộng, trừ hoặc lăn chuột để zoom quanh con trỏ. Giữ Space và kéo chuột trái để pan. Bạn có thể kéo, resize bounding box hoặc kéo từng đỉnh polygon. Fit to screen hiển thị toàn ảnh; 100% hiển thị một pixel ảnh tương ứng một CSS pixel.'},
  {id:'cau-hoi-vai-tro',question:'Thành viên trong workspace có quyền giống nhau không?',answer:'Không. Hệ thống có các vai trò Owner, Admin, Annotator, Reviewer và Viewer. Quyền thao tác phụ thuộc vai trò workspace và quyền trên annotation. Viewer chỉ xem dữ liệu. Vai trò quản trị workspace không đồng nghĩa với quản trị hệ thống.'},
  {id:'cau-hoi-export',question:'Dataset được xuất như thế nào?',answer:'Project hỗ trợ tải ZIP theo định dạng YOLO cho bounding box hoặc polygon. File ZIP có ảnh, nhãn và data.yaml. Cách chia train, validation và test được lưu lại để các lần export dùng nhất quán.'},
  {id:'cau-hoi-split',question:'Tôi có thể thay đổi tỷ lệ chia dataset không?',answer:'Có. Trong Dataset Export, nhập tỷ lệ train, validation và test rồi lưu split. Tỷ lệ mặc định là 80%, 10%, 10%; tổng phải bằng 100%. Mỗi ảnh chỉ thuộc một split. Ảnh không có đối tượng vẫn được đưa vào dataset.'},
  {id:'quyen-rieng-tu',question:'Dữ liệu của tôi được quản lý thế nào?',answer:'Ảnh, lớp nhãn và annotation nằm trong project thuộc workspace. API kiểm tra quyền truy cập đối với các thao tác dữ liệu; đăng nhập dùng session và cookie xác thực. Trang giới thiệu này chỉ hiển thị ảnh chụp với dữ liệu mẫu, không tải dataset riêng của bạn. Hãy hỏi người quản trị bản triển khai về chính sách lưu giữ, sao lưu và quyền riêng tư áp dụng.'},
  {id:'dieu-kien-su-dung',question:'Tôi bắt đầu sử dụng hệ thống ở đâu?',answer:'Chọn “Bắt đầu gán nhãn” để tạo tài khoản, rồi đăng nhập và làm việc trong workspace. Nếu đã đăng nhập, nút này mở workspace hiện tại. Việc xác minh email và khả năng gửi lời mời phụ thuộc cấu hình máy chủ. Người quản trị bản triển khai cung cấp các điều khoản sử dụng áp dụng cho hệ thống của bạn.'}
];
function Brand(){return <Link className="lp-brand" to="/" aria-label="AnnotateAI, trang chủ" aria-current="page"><img src="/favicon.svg" width="32" height="32" alt=""/>Annotate<span>AI</span></Link>;}
function Action({destination,small=false}:{destination:string;small?:boolean}){
  return <Link className={'lp-action'+(small?' lp-action-small':'')} to={destination}>Bắt đầu gán nhãn<span aria-hidden="true">↗</span></Link>;
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
      <nav className="lp-desktop-nav" aria-label="Điều hướng chính">{menuLinks}</nav>
      <div className="lp-nav-actions">{!signedIn&&<Link className="lp-login" to="/login">Đăng nhập</Link>}<Action destination={destination} small/></div>
      <button ref={toggle} className={'lp-menu-toggle'+(open?' is-open':'')} aria-label="Mở menu" aria-expanded={open} aria-controls="landing-mobile-nav" tabIndex={open?-1:0} onClick={()=>setOpen(true)}><span/><span/></button>
    </div>
    {open&&<div ref={panel} id="landing-mobile-nav" className="lp-mobile-panel" role="dialog" aria-modal="true" aria-label="Menu điều hướng" onKeyDown={event=>{
      if(event.key==='Escape'){event.preventDefault();close();}
      if(event.key==='Tab'){
        const elements=panel.current!.querySelectorAll<HTMLElement>('a,button'),first=elements[0],last=elements[elements.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    }}>
      <div className="lp-mobile-head"><Brand/><button className="lp-menu-toggle is-open" aria-label="Đóng menu" onClick={close}><span/><span/></button></div>
      <nav aria-label="Điều hướng di động">{menuLinks}{!signedIn&&<Link to="/login" style={{animationDelay:'240ms'}}>Đăng nhập</Link>}<Action destination={destination}/></nav>
      <p>Gán nhãn ảnh. Kiểm tra kết quả. Chuẩn bị dataset.</p>
    </div>}
  </header>;
}

function EditorScreenshot(){
  const [state,setState]=useState<'loading'|'loaded'|'error'>('loading');
  return <figure className="lp-product-shot" data-reveal>
    <div className="lp-shot-heading"><span><span className="lp-status-dot"/>AnnotateAI <span aria-hidden="true">/</span> Trình gán nhãn ảnh</span><span className="lp-shot-badge">Ảnh chụp giao diện</span></div>
    <div className="lp-shot-body" aria-busy={state==='loading'}>
      {state==='loading'&&<div className="lp-shot-skeleton" role="status"><span className="lp-sr-only">Đang tải ảnh giao diện…</span><i/><i/><i/></div>}
      {state!=='error'?<img className={state==='loaded'?'is-loaded':''} src="/landing/annotation-editor.png" width="1280" height="720" alt="Editor AnnotateAI với danh sách lớp nhãn, khung bao và polygon trên ảnh mẫu, cùng danh sách đối tượng ở bên phải" loading="eager" decoding="async" onLoad={()=>setState('loaded')} onError={()=>setState('error')}/>:<div className="lp-shot-error" role="status"><strong>Chưa tải được ảnh giao diện</strong><p>Bạn vẫn có thể đọc các tính năng và quy trình bên dưới.</p><a href="#chuc-nang">Xem tính năng đã có <span aria-hidden="true">↓</span></a></div>}
    </div>
    <figcaption><span>Editor thực tế với dữ liệu mẫu, ở chế độ chỉ xem.</span><span>Bounding box · Polygon · Lớp nhãn</span></figcaption>
  </figure>;
}
function FeaturesSection(){return <section id="chuc-nang" className="lp-section" aria-labelledby="lp-features-heading">
  <div className="lp-container"><div className="lp-section-intro" data-reveal><p className="lp-eyebrow">Từ thao tác vẽ đến dataset</p><h2 id="lp-features-heading">Công cụ cho từng bước<br/>chuẩn bị dữ liệu ảnh.</h2><p>Giữ ảnh, nhãn và công việc của nhóm trong cùng một hệ thống.</p></div>
    <div className="lp-feature-grid">{benefits.map((item,index)=><article className="lp-feature-card" key={item.title} data-reveal><div className="lp-feature-top"><span>0{index+1}</span><span>{item.tag}</span></div><h3>{item.title}</h3><p>{item.text}</p></article>)}</div>
  </div>
</section>;}
function Tagline(){
  const lines=['AI có thể gợi ý.','Chất lượng nhãn do bạn kiểm soát.'];
  let index=0;
  return <section className="lp-tagline-section" aria-labelledby="lp-tagline"><div className="lp-container">
    <p className="lp-eyebrow">Con người giữ vai trò quyết định</p>
    <h2 id="lp-tagline" aria-label={lines.join(' ')}>{lines.map(line=><span className="lp-tagline-line" aria-hidden="true" key={line}>{line.split(' ').map(word=><span data-word key={index} style={{transitionDelay:index++*45+'ms'}}>{word}{' '}</span>)}</span>)}</h2>
    <p>Đọc kết quả, sửa hình dạng và chọn lớp nhãn phù hợp trước khi đưa vào dataset.</p>
  </div></section>;
}
function WorkflowSection(){return <section id="quy-trinh" className="lp-section lp-workflow" aria-labelledby="lp-workflow-heading"><div className="lp-container">
  <div className="lp-section-intro" data-reveal><p className="lp-eyebrow">Quy trình làm việc</p><h2 id="lp-workflow-heading">Từ project đầu tiên<br/>đến file export.</h2></div>
  <ol className="lp-steps">{[
    ['Chuẩn bị ảnh và lớp nhãn','Tạo project trong workspace, chọn chế độ bounding box hoặc polygon, tải ảnh và thêm các lớp nhãn cần dùng.'],
    ['Gán nhãn, rà soát và chỉnh sửa','Vẽ thủ công hoặc chạy YOLO để nhận gợi ý. Kiểm tra, chấp nhận và chỉnh lại annotation theo quyền của bạn.'],
    ['Lưu split và xuất dataset','Đặt tỷ lệ train, validation và test. Lưu cách chia ảnh, rồi tải ZIP YOLO để dùng cho bước huấn luyện.']
  ].map(([title,text],index)=><li data-reveal key={title}><span className="lp-step-number">0{index+1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol>
  <div className="lp-export-panel" data-reveal><div><p className="lp-eyebrow">Một cách chia, dùng lại nhất quán</p><h3>Split được lưu theo từng ảnh.</h3><p>Điều chỉnh tỷ lệ trong project và export lại từ cách chia đã lưu.</p></div><div className="lp-split-example" aria-label="Tỷ lệ split mặc định, có thể thay đổi"><div className="lp-split-bar" aria-hidden="true"><span/><span/><span/></div><dl><div><dt>Train</dt><dd>80%</dd></div><div><dt>Validation</dt><dd>10%</dd></div><div><dt>Test</dt><dd>10%</dd></div></dl><p>Tỷ lệ mặc định. Có thể thay đổi trong Dataset Export.</p></div></div>
</div></section>;}
function CollaborationSection(){return <section id="cong-tac" className="lp-section lp-collaboration" aria-labelledby="lp-collab-heading"><div className="lp-container lp-collab-layout">
  <div className="lp-collab-copy" data-reveal><p className="lp-eyebrow">Cùng làm, rõ quyền</p><h2 id="lp-collab-heading">Một workspace.<br/>Mỗi người một vai trò.</h2><p>Mời thành viên vào workspace, quản lý project và phân quyền theo công việc của nhóm.</p><ul><li>Quyền xem, gán nhãn và quản lý theo vai trò.</li><li>Thông tin người tạo và người chỉnh sửa trên annotation.</li><li>Rà soát và sửa nhãn trong cùng editor.</li></ul></div>
  <div className="lp-role-panel" data-reveal><div className="lp-role-heading"><span>Vai trò trong workspace</span><span className="lp-role-mark" aria-hidden="true">↗</span></div><dl>{[
    ['Owner','Chủ workspace'],['Admin','Quản trị workspace'],['Annotator','Người gán nhãn'],['Reviewer','Người rà soát'],['Viewer','Người xem']
  ].map(([role,label])=><div key={role}><dt>{role}</dt><dd>{label}</dd></div>)}</dl><p>Quản trị workspace và quản trị hệ thống là hai quyền riêng biệt.</p></div>
</div></section>;}
function FAQSection(){return <section id="hoi-dap" className="lp-section lp-faq" aria-labelledby="lp-faq-heading"><div className="lp-container lp-faq-layout"><div className="lp-section-intro" data-reveal><p className="lp-eyebrow">Trước khi bắt đầu</p><h2 id="lp-faq-heading">Những điều<br/>bạn muốn biết.</h2><p>Tính năng, quyền truy cập và cách sử dụng dữ liệu.</p></div><div className="lp-faq-list" data-reveal>{questions.map(item=><details key={item.id} id={item.id}><summary>{item.question}<span aria-hidden="true">+</span></summary><p>{item.answer}</p></details>)}</div></div></section>;}

export default function LandingPage(){
  const {user,initializing}=useAuth();
  // Keep the existing landing destinations; login routing remains in authentication.
  const destination=user?'/projects':'/register';
  const root=useRef<HTMLDivElement>(null),[active,setActive]=useState('');
  useEffect(()=>{
    const oldTitle=document.title,oldLang=document.documentElement.lang;
    document.title='AnnotateAI | Gán nhãn ảnh và chuẩn bị dataset YOLO';
    document.documentElement.lang='vi';
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
    <a className="lp-skip" href="#main-content">Đến nội dung chính</a>
    <LandingNavbar destination={destination} signedIn={!!user} active={active}/>
    <main id="main-content" tabIndex={-1}>
      <section id="gioi-thieu" className="lp-hero" aria-labelledby="lp-title"><div className="lp-container">
        <div className="lp-hero-layout"><div className="lp-hero-copy"><p className="lp-eyebrow"><span className="lp-status-dot"/>Workspace cho nhóm thị giác máy tính</p><h1 id="lp-title">Rõ từng nhãn ảnh.<br/>Sẵn sàng cho YOLO.</h1><p>Gán bounding box, vẽ polygon và rà soát gợi ý YOLO. Quản lý ảnh, lớp nhãn và cộng tác trong cùng workspace.</p><div className="lp-hero-action">{initializing?<span className="lp-action-skeleton" role="status">Đang kiểm tra phiên…</span>:<Action destination={destination}/>}<span>{user?'Tiếp tục làm việc trong workspace của bạn.':'Tạo tài khoản để bắt đầu trong workspace của bạn.'}</span></div></div>
          <EditorScreenshot/>
        </div>
      </div></section>
      <FeaturesSection/><Tagline/><WorkflowSection/><CollaborationSection/><FAQSection/>
      <section className="lp-section lp-final" aria-labelledby="lp-final-heading"><div className="lp-container" data-reveal><p className="lp-eyebrow">Bắt đầu từ project của bạn</p><h2 id="lp-final-heading">Đưa ảnh vào workspace.<br/>Bắt tay vào gán nhãn.</h2><p>Tạo project, chọn lớp nhãn và chuẩn bị bộ dữ liệu cho bước tiếp theo.</p><Action destination={destination}/><span>{user?'Mở workspace để tiếp tục công việc.':'Bạn sẽ đến trang tạo tài khoản.'}</span></div></section>
    </main>
    <footer className="lp-footer"><div className="lp-container"><div className="lp-footer-top"><div><Brand/><p>Không gian gán nhãn ảnh<br/>cho nhóm thị giác máy tính.</p></div><nav aria-label="Điều hướng cuối trang"><a href="#chuc-nang">Tính năng</a><a href="#quy-trinh">Quy trình</a><a href="#hoi-dap">Hỏi đáp</a><Link to="/login">Đăng nhập</Link></nav></div><div className="lp-footer-bottom"><span>© {new Date().getFullYear()} AnnotateAI</span><div><a href="#quyen-rieng-tu" onClick={()=>openDisclosure('quyen-rieng-tu')}>Quyền riêng tư</a><a href="#dieu-kien-su-dung" onClick={()=>openDisclosure('dieu-kien-su-dung')}>Điều kiện sử dụng</a><a href="#main-content">Về đầu trang ↑</a></div></div></div></footer>
    <script type="application/ld+json">{JSON.stringify(schema)}</script>
  </div>;
}
