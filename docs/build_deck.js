const pptxgen = require('pptxgenjs');
const p = new pptxgen(); p.layout = 'LAYOUT_WIDE'; p.title = 'The Campaign Provisioner';
const F = 'Calibri', NAVY='1F3A8A', BLUE='2563EB', PURPLE='6D28D9', INK='1E293B', MUTE='64748B', LIGHT='EFF4FF', LILAC='F3EEFF', LINE='93A8D8';

// ---------- Slide 1: title ----------
let s = p.addSlide(); s.background = {color: '4C1D95'};
s.addText('The Campaign Provisioner', {x:0.9,y:2.3,w:11,h:1,fontFace:F,fontSize:44,bold:true,color:'FFFFFF',margin:0,isTextBox:true});
s.addText('An Autonomous Marketing Logistics Agent for Inventory, Procurement and Budget Approval', {x:0.9,y:3.4,w:10.5,h:0.9,fontFace:F,fontSize:22,color:'FFFFFF',margin:0,isTextBox:true});
s.addText('User Persona: Marketing Manager, Campaign Planner, Finance Approver', {x:0.9,y:4.6,w:10.5,h:0.5,fontFace:F,fontSize:18,color:'DDD6FE',margin:0,isTextBox:true});
s.addNotes('Title slide. Replace with your own template title slide and copy the text across.');

// ---------- Slide 2: overview ----------
s = p.addSlide(); s.background = {color:'FFFFFF'};
s.addText('The Campaign Provisioner', {x:0.6,y:0.4,w:7,h:0.7,fontFace:F,fontSize:30,color:INK,margin:0,isTextBox:true});
s.addText([
 {text:'Campaign logistics are slow and fragmented. Teams chase stock levels in one system, vendor quotes in another and budget sign-off by email, so launches slip and spend goes unchecked.', options:{bullet:true,breakLine:true,paraSpaceAfter:14}},
 {text:'The agent works as an autonomous logistics coordinator. A central orchestrator registers each campaign request and governs three specialist sub-agents: Inventory checks and reserves stock, Procurement gets vendor quotes and places purchase orders, and Budget validates funds. Spend above the high-value threshold pauses for a human approver, and no purchase order can be placed without an approved budget.', options:{bullet:true}}
], {x:0.6,y:1.4,w:6.2,h:5.2,fontFace:F,fontSize:16,color:INK,valign:'top',margin:0,isTextBox:true});
s.addShape(p.ShapeType.rect,{x:7.2,y:0,w:6.13,h:7.5,fill:{color:'2B4BD8'},line:{color:'2B4BD8'}});
const pillars = [
 ['1','Autonomous Stock & Sourcing','Checks live stock, reserves available units and calculates shortfalls. Procurement compares vendor quotes on price and lead time and recommends the best fit for the campaign date.'],
 ['2','Governed Budget Approval','Validates the campaign budget and approves routine spend by policy. High-value requests pause for a named human approver with the full justification, and rejected requests stop the workflow.'],
 ['3','Controlled Execution & Audit','Purchase orders are hard-blocked until an approved budget covers them. Every action is logged to an audit trail, and the orchestrator returns one consolidated summary of stock, orders and remaining budget.']];
pillars.forEach((q,i)=>{ const y=0.7+i*2.15;
 s.addText(q[0],{x:7.5,y:y+0.35,w:0.6,h:0.8,fontFace:F,fontSize:40,color:'FFFFFF',margin:0,isTextBox:true});
 s.addText(q[1],{x:8.2,y:y,w:4.7,h:0.45,fontFace:F,fontSize:18,bold:true,color:'FFFFFF',margin:0,isTextBox:true});
 s.addText(q[2],{x:8.2,y:y+0.5,w:4.7,h:1.4,fontFace:F,fontSize:12,color:'FFFFFF',valign:'top',margin:0,isTextBox:true});
 if(i<2) s.addShape(p.ShapeType.line,{x:8.2,y:y+1.98,w:4.7,h:0,line:{color:'FFFFFF',width:1}});
});
s.addNotes('Overview slide: problem, how the agent works, and the three capability pillars.');

// ---------- Slide 3: reference architecture (all native, editable shapes) ----------
s = p.addSlide(); s.background = {color:'FFFFFF'};
const box=(x,y,w,h,o={})=>s.addShape(o.round?p.ShapeType.roundRect:p.ShapeType.rect,{x,y,w,h,rectRadius:o.round?0.06:undefined,fill:{color:o.fill||'FFFFFF'},line:{color:o.line||LINE,width:o.lw||1,dashType:o.dash}});
const txt=(t,x,y,w,h,o={})=>s.addText(t,{x,y,w,h,fontFace:F,fontSize:o.sz||9,bold:o.b,color:o.c||INK,align:o.al||'center',valign:o.va||'middle',margin:o.m??2,isTextBox:true,italic:o.i});
const card=(x,y,w,h,title,sub,o={})=>{box(x,y,w,h,{round:true,fill:o.fill||'FFFFFF',line:o.line||LINE}); txt(title,x+0.05,y+0.04,w-0.1,sub?h*0.5:h-0.08,{b:true,sz:o.sz||9,al:o.al}); if(sub) txt(sub,x+0.05,y+h*0.5,w-0.1,h*0.45,{sz:8,c:MUTE,va:'top',al:o.al});};
const arrow=(x1,y1,x2,y2,both)=>s.addShape(p.ShapeType.line,{x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1),h:Math.abs(y2-y1),flipH:x2<x1,flipV:y2<y1,line:{color:BLUE,width:1.5,endArrowType:'triangle',beginArrowType:both?'triangle':undefined}});

txt('The Campaign Provisioner Agent : Reference Architecture',0.5,0.2,12.3,0.6,{sz:26,c:BLUE,al:'center'});
s.addShape(p.ShapeType.line,{x:0.5,y:0.9,w:12.3,h:0,line:{color:'D1D5DB',width:0.75}});

// Left: users & interfaces
box(0.4,2.5,2.0,2.3,{fill:LIGHT}); 
txt('Users & Channels',0.45,2.55,1.9,0.3,{b:true,sz:11,c:NAVY});
txt('Marketing Manager,\nCampaign Planner,\nFinance Approver (HITL)',0.45,2.9,1.9,0.8,{sz:9,b:true});
txt('Interfaces',0.45,3.75,1.9,0.3,{b:true,sz:11,c:NAVY});
card(0.55,4.05,1.7,0.3,'Gemini Enterprise App',null,{sz:8});
card(0.55,4.4,1.7,0.3,'Custom Apps / ADK Web',null,{sz:8});
arrow(2.4,3.2,2.95,3.2); txt('Request',2.35,2.95,0.6,0.2,{sz:7,c:MUTE});
arrow(2.95,3.9,2.4,3.9); txt('Results',2.35,3.95,0.6,0.2,{sz:7,c:MUTE});

// Center: Google Cloud runtime
box(2.95,1.05,7.4,5.55,{fill:'FFFFFF',line:BLUE,lw:1.25});
txt('Google Cloud ( Agent Runtime )',2.95,1.08,7.4,0.3,{b:true,sz:10});
// root agent
box(3.1,1.45,7.1,1.2,{fill:LIGHT});
txt('Root Agent',3.15,1.38,0.9,0.22,{sz:8,b:true,c:'FFFFFF'}); 
s.addShape(p.ShapeType.roundRect,{x:3.15,y:1.38,w:1.0,h:0.22,rectRadius:0.05,fill:{color:BLUE},line:{color:BLUE}});
txt('Root Agent',3.15,1.38,1.0,0.22,{sz:8,b:true,c:'FFFFFF'});
txt('Campaign Provisioner Agent (Orchestrator)',3.2,1.62,6.9,0.3,{sz:13,c:NAVY,b:true});
['Greeting & Intent','Multi-Agent Coordination','State Coordination','Human Approval Gate','Result Aggregation'].forEach((t,i)=>card(3.25+i*1.37,2.0,1.3,0.45,t,null,{sz:8}));
// sub agents
box(3.1,2.8,7.1,2.05,{fill:'E8F0FF',line:LINE,dash:'dash'});
s.addShape(p.ShapeType.roundRect,{x:3.15,y:2.73,w:1.0,h:0.22,rectRadius:0.05,fill:{color:BLUE},line:{color:BLUE}}); txt('3 Sub Agents',3.15,2.73,1.0,0.22,{sz:8,b:true,c:'FFFFFF'});
const subs=[['1. Inventory Agent','(Check & Reserve Stock)',['Check live stock by SKU','Reserve available units','Report shortfall to procure'],'F0F7FF'],
 ['2. Procurement Agent','(Quote & Place PO)',['Fetch vendor quotes','Rank on price & lead time','Place PO only if approved'],LILAC],
 ['3. Budget Agent','(Validate & Approve - HITL)',['Check remaining budget','Auto-approve under threshold','Human approval above threshold'],'FFF7ED']];
subs.forEach((q,i)=>{ const x=3.2+i*2.33; box(x,3.05,2.25,1.7,{fill:q[3],line:LINE});
 txt(q[0],x+0.05,3.08,2.15,0.28,{b:true,sz:10,c:PURPLE}); txt(q[1],x+0.05,3.34,2.15,0.22,{sz:8,c:PURPLE});
 box(x+0.1,3.62,2.05,1.05,{fill:'FFFFFF',line:'D6E0F5'});
 s.addText(q[2].map((t,j)=>({text:t,options:{bullet:true,breakLine:j<2}})),{x:x+0.15,y:3.66,w:1.95,h:0.97,fontFace:F,fontSize:8.5,color:INK,valign:'middle',margin:2,isTextBox:true});});
arrow(6.65,2.45,6.65,2.8,true);
// memory
box(3.1,4.95,7.1,0.8,{fill:LIGHT}); txt('Memory & Knowledge Layer',3.1,4.95,7.1,0.25,{b:true,sz:9,c:NAVY});
[['Budget Policy & Thresholds','High-value limit, approval rules'],['Session Working Memory','Request state, approvals, POs'],['Audit Trail & Artifact Cache','Actions, quotes, summaries']].forEach((q,i)=>card(3.3+i*2.25,5.2,2.15,0.5,q[0],q[1],{sz:8}));
// cloud services
box(3.1,5.82,7.1,0.7,{fill:LIGHT}); txt('Google Cloud Supporting Services',3.1,5.82,7.1,0.22,{b:true,sz:9,c:NAVY});
[['IAM','Access Control'],['Secret Manager','Credentials'],['Cloud Logging','Audit Trail'],['Cloud Monitoring','Observability'],['Cloud Trace','Tracing'],['Model Armor','Safety Filtering']].forEach((q,i)=>card(3.2+i*1.15,6.03,1.08,0.5,q[0],q[1],{sz:7}));

// MCP rail
box(10.45,1.5,0.3,4.6,{round:true,fill:'FFFFFF',line:BLUE});
s.addText('MCP / Tool Calls',{x:10.45,y:1.5,w:0.3,h:4.6,fontFace:F,fontSize:8,color:BLUE,align:'center',valign:'middle',margin:0,isTextBox:true,vert:'vert270'});
arrow(10.2,3.3,10.45,3.3,true);

// Right column
const rcol=(y,h,title,items)=>{ box(10.9,y,2.1,h,{fill:LIGHT}); txt(title,10.95,y+0.03,2.0,0.28,{b:true,sz:9,c:NAVY});
 items.forEach((q,i)=>card(11.0,y+0.35+i*0.62,1.9,0.55,q[0],q[1],{sz:8}));};
rcol(1.05,2.0,'Enterprise Data Integration',[['ERP / Inventory System','Stock levels, reservations'],['Vendor Catalog / Procurement','Quotes, purchase orders'],]);
rcol(3.2,2.0,'Action & Execution Layer',[['Purchase Order API','Place and track POs'],['Approval Workflow','HITL request & decision']]);
rcol(5.35,1.25,'LLM & AI Framework',[['Gemini  |  ADK 2.x','Reasoning & Agent Framework']]);
arrow(10.75,2.0,10.9,2.0,true); arrow(10.75,4.1,10.9,4.1,true); arrow(10.75,5.95,10.9,5.95,true);
txt('HCLTech  |  Confidential',0.5,6.95,5,0.3,{sz:9,al:'left',c:MUTE});
s.addNotes('Reference architecture. Every element is a native, editable PowerPoint shape or text box - no images.');
p.writeFile({fileName:'/home/user/market-campaign-agent/docs/Campaign_Provisioner_Management_Deck.pptx'}).then(()=>console.log('ok'));
