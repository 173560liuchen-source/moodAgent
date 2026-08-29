import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = async (name) => readFile(path.join(root, name), 'utf8');

test('首页登录入口与受保护页面鉴权守卫存在', async () => {
  const home = await source('index.html');
  const login = await source('login.html');
  const guard = await source('auth-guard.js');
  const app = await source('app.html');
  assert.match(home, /textContent='登录';a\.href='#login'/);
  assert.match(home, /id="auth-modal"/);
  assert.match(home, /entry\.href='transition\.html'/);
  assert.match(home, /returnTarget=.*:'transition\.html'/);
  assert.match(home, /activeLink\.href='transition\.html'/);
  assert.match(guard, /index\.html\?login=1/);
  assert.match(login, /\/auth\/\$\{mode\}/);
  assert.match(guard, /Authorization/);
  assert.match(guard, /index\.html\?login=1&return=/);
  assert.match(app, /auth-guard\.js/);
});

test('聊天页包含流式主流程和可访问的消息区域', async () => {
  const page = await source('app.html');
  assert.match(page, /class="messages"/);
  assert.match(page, /agent\/gateway\/orchestrate\/stream/);
  assert.match(page, /agent\/gateway\/init\/stream/);
  assert.match(page, /text\/event-stream/);
  assert.match(page, /packet\.event==='delta'/);
  assert.doesNotMatch(page, /history:\[\.\.\.history\]/);
});

test('风险页连接真实风险中心、热线和预约入口', async () => {
  const page = await source('risk-recognition.html');
  const script = await source('risk-recognition.js');
  assert.match(page, /id="refresh-risk"/);
  assert.match(page, /id="hotline-list"/);
  assert.match(script, /agent\/insights\/risk-center/);
  assert.match(script, /help\/hotline/);
  assert.match(script, /help\/appoint/);
});

test('干预页能够读取方案并提交执行反馈', async () => {
  const page = await source('intervention.html');
  const script = await source('intervention.js');
  assert.match(page, /id="history-list"/);
  assert.match(page, /id="action-list"/);
  assert.match(page, /feedback-details/);
  assert.match(script, /agent\/insights\/session-center/);
  assert.match(script, /agent\/insights\/intervention-feedback/);
  assert.match(script, /填写执行反馈/);
});

test('测评页包含量表加载、提交和历史记录入口', async () => {
  const page = await source('assessment.html');
  const script = await source('assessment.js');
  assert.match(page, /id="question-list"/);
  assert.match(page, /id="history-list"/);
  assert.match(script, /assessment\/questions/);
  assert.match(script, /assessment\/submit/);
  assert.match(script, /api\/assessment\/list/);
});

test('算法测评页单列 RAG 检索与可信回答专项结果', async () => {
  const page = await source('evaluation.html');
  const script = await source('evaluation.js');
  assert.match(page, /RAG 检索与可信回答测试/);
  assert.match(page, /id="rag-grid"/);
  assert.match(script, /function renderRag\(data\)/);
  assert.match(script, /rag_document_recall_at_5/);
  assert.match(script, /rag_abstention_accuracy/);
  assert.match(script, /rag_retrieval_error_rate/);
});

test('审计页展示风险约束路由的可追溯依据', async () => {
  const page = await source('audit-log.html');
  const script = await source('audit-log.js');
  assert.match(page, /audit-log\.js/);
  assert.match(script, /audit\.routing\|\|detail\.routing/);
  assert.match(script, /本次路径依据/);
  assert.match(script, /风险约束路由/);
  assert.match(script, /risk_router_hard_constraint/);
});

test('聊天管理将并行初始分析拆分并显示 RAG 节点', async () => {
  const script = await source('chat-management.js');
  assert.match(script, /ragWasExecuted/);
  assert.match(script, /expandTimeline/);
  assert.match(script, /rag_agent:'RAG 知识检索'/);
  assert.match(script, /keyResultLabels=.*安全检查/);
  assert.match(script, /知识检索与引用/);
  assert.match(script, /detail\.audit\?\.routing\?\.selected_route/);
});

test('聊天管理使用列表索引区分具有相同 session_id 的记录', async () => {
  const script = await source('chat-management.js');
  assert.match(script, /state\.selected===session/);
  assert.match(script, /data-index="\$\{index\}"/);
  assert.match(script, /state\.filtered\[index\]/);
  assert.doesNotMatch(script, /find\(s=>String\(s\.session_id\)===card\.dataset\.id\)/);
});
