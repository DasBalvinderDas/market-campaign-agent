const pptxgen = require('pptxgenjs');
const p = new pptxgen(); p.layout = 'LAYOUT_WIDE'; p.title = 'The LaunchKit Provisioner';
const F = 'Calibri', NAVY='1F3A8A', BLUE='2563EB', PURPLE='6D28D9', INK='1E293B', MUTE='64748B', LIGHT='EFF4FF', LILAC='F3EEFF', LINE='93A8D8';

// ---------- Slide 1: title ----------
let s = p.addSlide(); s.background = {color: '4C1D95'};
s.addText('The LaunchKit Provisioner', {x:0.9,y:2.3,w:11,h:1,fontFace:F,fontSize:44,bold:true,color:'FFFFFF',margin:0,isTextBox:true});
s.addText('An event procurement agent on BigQuery and Application Integration: one event brief, many vendors, three plain-English options, approval by order size, bulk orders placed automatically', {x:0.9,y:3.4,w:10.5,h:0.9,fontFace:F,fontSize:22,color:'FFFFFF',margin:0,isTextBox:true});
s.addText('User Persona: Product Marketing Manager, Brand Director, VP / CMO approver', {x:0.9,y:4.6,w:10.5,h:0.5,fontFace:F,fontSize:18,color:'DDD6FE',margin:0,isTextBox:true});
s.addNotes('Title slide. Replace with your own template title slide and copy the text across.');

// ---------- Slide 2: overview ----------
s = p.addSlide(); s.background = {color:'FFFFFF'};
s.addText('The LaunchKit Provisioner', {x:0.6,y:0.4,w:7,h:0.7,fontFace:F,fontSize:30,color:INK,margin:0,isTextBox:true});
s.addText([
 {text:'A big event, such as a product launch, needs many different items from many vendors, delivered to guests, venues and sales teams in several regions before a hard deadline. Teams buy item by item, juggle sizes, vendor lead times and surplus stock in different warehouses, and the only question finance sees is "approve this spend?".', options:{bullet:true,breakLine:true,paraSpaceAfter:14}},
 {text:'Underneath it is still a purchase order, procurement and approval system, but it takes a WHOLE EVENT instead of single items. A central orchestrator turns the brief into a shopping list / Bill of Materials (Brief Analyst), compares many vendors and computes three plain-English options from BigQuery data (Sourcing Planner: buying everything new, use our stock first, buy the rest, certified green option), lets the Product Marketing Manager choose, gets a named executive to sign off above the autopilot limit, and has the orders placed (Fulfilment). Purchase orders, depot transfers, the sign-off email and the tracking update run as Google Application Integration workflows. The orchestrator is the only agent that can authorise spend.', options:{bullet:true}}
], {x:0.6,y:1.4,w:6.2,h:5.2,fontFace:F,fontSize:15,color:INK,valign:'top',margin:0,isTextBox:true});
s.addShape(p.ShapeType.rect,{x:7.2,y:0,w:6.13,h:7.5,fill:{color:'2B4BD8'},line:{color:'2B4BD8'}});
const pillars = [
 ['1','Deadline-first planning','Every option is costed against the in-hand date: cost, delivery date, safety buffer in hours, risk and carbon are computed from BigQuery, never typed in. Vendor delays re-plan the options in seconds.'],
 ['2','Surplus before new spend','Spare packaging, folders and adapters in regional depots are reused first, nearest depot first, and held while a sign-off is pending. The rebalance option saves cost and often arrives earlier.'],
 ['3','A decision, not a yes / no','The manager picks one of three computed options. Small spend runs on autopilot; above the limit a VP (or the CMO for the largest option) signs off by email. Orders, transfers and the audit trail follow automatically.']];
pillars.forEach((q,i)=>{ const y=0.7+i*2.15;
 s.addText(q[0],{x:7.5,y:y+0.35,w:0.6,h:0.8,fontFace:F,fontSize:40,color:'FFFFFF',margin:0,isTextBox:true});
 s.addText(q[1],{x:8.2,y:y,w:4.7,h:0.45,fontFace:F,fontSize:18,bold:true,color:'FFFFFF',margin:0,isTextBox:true});
 s.addText(q[2],{x:8.2,y:y+0.5,w:4.7,h:1.4,fontFace:F,fontSize:12,color:'FFFFFF',valign:'top',margin:0,isTextBox:true});
 if(i<2) s.addShape(p.ShapeType.line,{x:8.2,y:y+1.98,w:4.7,h:0,line:{color:'FFFFFF',width:1}});
});
s.addNotes('Overview slide: the problem, how the agent works, and the three capability pillars. Fictional demo launch: Spring Launch Event. All data is demo data.');

// ---------- Slide 3: reference architecture (all native, editable shapes) ----------
s = p.addSlide(); s.background = {color:'FFFFFF'};
const box=(x,y,w,h,o={})=>s.addShape(o.round?p.ShapeType.roundRect:p.ShapeType.rect,{x,y,w,h,rectRadius:o.round?0.06:undefined,fill:{color:o.fill||'FFFFFF'},line:{color:o.line||LINE,width:o.lw||1,dashType:o.dash}});
const txt=(t,x,y,w,h,o={})=>s.addText(t,{x,y,w,h,fontFace:F,fontSize:o.sz||9,bold:o.b,color:o.c||INK,align:o.al||'center',valign:o.va||'middle',margin:o.m??2,isTextBox:true,italic:o.i});
const card=(x,y,w,h,title,sub,o={})=>{box(x,y,w,h,{round:true,fill:o.fill||'FFFFFF',line:o.line||LINE}); txt(title,x+0.05,y+0.04,w-0.1,sub?h*0.45:h-0.08,{b:true,sz:o.sz||9,al:o.al}); if(sub) txt(sub,x+0.05,y+h*0.47,w-0.1,h*0.5,{sz:o.ssz||7.5,c:MUTE,va:'top',al:o.al});};
const arrow=(x1,y1,x2,y2,both)=>s.addShape(p.ShapeType.line,{x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1),h:Math.abs(y2-y1),flipH:x2<x1,flipV:y2<y1,line:{color:BLUE,width:1.5,endArrowType:'triangle',beginArrowType:both?'triangle':undefined}});

txt('The LaunchKit Provisioner : Reference Architecture',0.5,0.2,12.3,0.6,{sz:26,c:BLUE,al:'center'});
s.addShape(p.ShapeType.line,{x:0.5,y:0.9,w:12.3,h:0,line:{color:'D1D5DB',width:0.75}});

// Left: users & interfaces
box(0.4,2.5,2.0,2.3,{fill:LIGHT});
txt('Users & Channels',0.45,2.55,1.9,0.3,{b:true,sz:11,c:NAVY});
txt('Product Marketing\nManager, Brand Director',0.45,2.9,1.9,0.8,{sz:9,b:true});
txt('Interfaces',0.45,3.75,1.9,0.3,{b:true,sz:11,c:NAVY});
card(0.55,4.05,1.7,0.3,'Gemini Enterprise App',null,{sz:8});
card(0.55,4.4,1.7,0.3,'Custom Apps / ADK Web',null,{sz:8});
arrow(2.4,3.2,2.95,3.2); txt('Brief',2.35,2.95,0.6,0.2,{sz:7,c:MUTE});
arrow(2.95,3.9,2.4,3.9); txt('Options',2.35,3.95,0.6,0.2,{sz:7,c:MUTE});

// Left: executive sign-off (native Application Integration approval)
box(0.4,5.0,2.0,1.35,{fill:LIGHT});
txt('Sign-off (HITL)',0.45,5.03,1.9,0.28,{b:true,sz:10,c:NAVY});
card(0.55,5.32,1.7,0.42,'VP / CMO: Approve / Reject email',null,{sz:7.5});
card(0.55,5.8,1.7,0.45,'Approval task','Application Integration',{sz:8});
arrow(2.4,5.95,2.95,5.95);

// Center: Google Cloud runtime
box(2.95,1.05,7.4,5.55,{fill:'FFFFFF',line:BLUE,lw:1.25});
txt('Google Cloud ( Vertex AI Agent Engine runtime )',2.95,1.08,7.4,0.3,{b:true,sz:10});
box(3.1,1.45,7.1,1.2,{fill:LIGHT});
s.addShape(p.ShapeType.roundRect,{x:3.15,y:1.38,w:1.0,h:0.22,rectRadius:0.05,fill:{color:BLUE},line:{color:BLUE}});
txt('Root Agent',3.15,1.38,1.0,0.22,{sz:8,b:true,c:'FFFFFF'});
txt('LaunchKit Provisioner (Orchestrator)',3.2,1.64,6.9,0.34,{sz:13,c:NAVY,b:true});
box(3.25,2.02,6.8,0.5,{round:true,fill:'FFFFFF',line:LINE});
txt([{text:'Responsibilities of this single agent:  ',options:{bold:true,color:NAVY}},{text:'Hello card  •  Coordination  •  3-choices table  •  Sign-off gate (automatic, VP, CMO)  •  Order story & status',options:{color:INK}}],3.3,2.04,6.7,0.46,{sz:8.5});

// specialist agents
box(3.1,2.8,7.1,2.05,{fill:'E8F0FF',line:LINE,dash:'dash'});
s.addShape(p.ShapeType.roundRect,{x:3.15,y:2.73,w:3.0,h:0.22,rectRadius:0.05,fill:{color:BLUE},line:{color:BLUE}}); txt('3 Sub Agents (called by the root as tools)',3.15,2.73,3.0,0.22,{sz:8,b:true,c:'FFFFFF'});
const subs=[['1. Brief Analyst','(Decompose the brief)',['Shopping list (Bill of Materials)','Sizes and plugs from the guest list','Requirement lines per region'],'F0F7FF'],
 ['2. Sourcing Planner','(Compute 3 options)',['Vendor comparison report','Reuse our own stock first','Price, spare time, pollution'],LILAC],
 ['3. Fulfilment Agent','(Place the orders)',['PO per vendor line (App Integration)','Warehouse move per surplus line','HTML update + order story'],'FFF7ED']];
subs.forEach((q,i)=>{ const x=3.2+i*2.33; box(x,3.05,2.25,1.7,{fill:q[3],line:LINE});
 txt(q[0],x+0.05,3.08,2.15,0.28,{b:true,sz:10,c:PURPLE}); txt(q[1],x+0.05,3.34,2.15,0.22,{sz:8,c:PURPLE});
 box(x+0.1,3.62,2.05,1.05,{fill:'FFFFFF',line:'D6E0F5'});
 s.addText(q[2].map((t,j)=>({text:t,options:{bullet:true,breakLine:j<2}})),{x:x+0.15,y:3.66,w:1.95,h:0.97,fontFace:F,fontSize:8.5,color:INK,valign:'middle',margin:2,isTextBox:true});});
arrow(6.65,2.45,6.65,2.8,true);

// memory
box(3.1,4.95,7.1,0.8,{fill:LIGHT}); txt('Memory & Knowledge Layer',3.1,4.95,7.1,0.25,{b:true,sz:9,c:NAVY});
[['Scenarios & plan lines (BigQuery)','Computed options per request'],['Agent Engine Sessions','Chat state'],['Audit Log (BigQuery)','Every governed action']].forEach((q,i)=>card(3.3+i*2.25,5.2,2.15,0.5,q[0],q[1],{sz:8}));
// cloud services
box(3.1,5.82,7.1,0.7,{fill:LIGHT}); txt('Google Cloud Supporting Services',3.1,5.82,7.1,0.22,{b:true,sz:9,c:NAVY});
[['IAM','Access Control'],['Secret Manager','Credentials'],['Cloud Logging','Audit Trail'],['Cloud Monitoring','Observability'],['Cloud Trace','Tracing'],['Model Armor','Safety Filtering']].forEach((q,i)=>card(3.2+i*1.15,6.03,1.08,0.5,q[0],q[1],{sz:7}));

// API rail
box(10.45,1.5,0.3,4.6,{round:true,fill:'FFFFFF',line:BLUE});
s.addText('BigQuery API  |  Application Integration API',{x:10.45,y:1.5,w:0.3,h:4.6,fontFace:F,fontSize:8,color:BLUE,align:'center',valign:'middle',margin:0,isTextBox:true,vert:'vert270'});
arrow(10.2,3.3,10.45,3.3,true);

// Right column: BigQuery schema (new) and Application Integration
box(10.9,1.05,2.3,3.35,{fill:LIGHT}); txt('Google BigQuery (launchkit)',10.95,1.08,2.2,0.28,{b:true,sz:9,c:NAVY});
card(11.0,1.38,2.1,0.98,'Reference data','launches, assets, bundle_templates, guests, depots, depot_stock, transit_lanes, vendors, vendor_offers, planning_rules, approval_policy, approvers',{sz:8,ssz:6.5});
card(11.0,2.41,2.1,0.72,'Plan & decision','scenarios, scenario_lines, decisions, depot_holds, vendor_disruptions',{sz:8,ssz:6.5});
card(11.0,3.18,2.1,0.55,'Orders & audit','purchase_orders, depot_transfers, audit_log',{sz:8,ssz:6.5});
card(11.0,3.78,2.1,0.55,'Views','v_depot_available, v_launch_readiness',{sz:8,ssz:6.5});
box(10.9,4.5,2.3,1.8,{fill:LIGHT}); txt('Application Integration',10.95,4.53,2.2,0.28,{b:true,sz:9,c:NAVY});
card(11.0,4.83,2.1,0.33,'create_purchase_order',null,{sz:8}); card(11.0,5.2,2.1,0.33,'create_depot_transfer',null,{sz:8});
card(11.0,5.57,2.1,0.33,'request_approval (Approve / Reject)',null,{sz:7.5}); card(11.0,5.94,2.1,0.3,'send_launch_update',null,{sz:7.5});
box(10.9,6.4,2.3,0.5,{fill:LIGHT}); txt('Gemini  |  ADK 2.x',10.95,6.42,2.2,0.46,{b:true,sz:8.5,c:NAVY});
arrow(10.75,2.6,10.9,2.6,true); arrow(10.75,5.2,10.9,5.2,true);
txt('HCLTech  |  Confidential',0.5,6.95,5,0.3,{sz:9,al:'left',c:MUTE});
s.addNotes('Reference architecture. Every element is a native, editable PowerPoint shape or text box - no images. BigQuery (dataset launchkit) holds all data: reference data (launches, assets, bundle templates, guests, depots and stock, transit lanes, vendors and offers, planning rules, approval policy, approvers), the computed plan (scenarios, scenario lines, decisions, depot holds, vendor disruptions) and the orders and audit log. The root agent calls the three specialist agents as tools, so it writes every reply on every platform including Gemini Enterprise. Application Integration runs four workflows: create_purchase_order, create_depot_transfer, request_approval (a native Approval task that emails the executive Approve / Reject and waits) and send_launch_update.');
p.writeFile({fileName:'/home/user/market-campaign-agent/docs/LaunchKit_Provisioner_Management_Deck.pptx'}).then(()=>console.log('ok'));
