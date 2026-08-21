#!/usr/bin/env node
/*
 * generate_forms.js
 *
 * 用 kuromoji 对 lyrics/*.md 的「日文歌词」做分词，
 * 自动提取词表中动词/惯用表达在歌词里实际出现的语法形态，
 * 并记录一个出现该形态的歌名。
 *
 * 用法（先在项目目录安装 kuromoji）：
 *   npm install kuromoji@0.1.2 --no-workspaces
 *   node generate_forms.js
 *
 * 输出：forms.json
 *   { "出会う": { "出会った": "Returns", "出会って": "Future Place", ... }, ... }
 */
const fs = require('fs');
const path = require('path');
const kuromoji = require('kuromoji');

const HERE = __dirname;
const VOCAB_PATH = path.join(HERE, 'vocab.json');
const LYRICS_DIR = path.join(HERE, 'lyrics');
const OUT_PATH = path.join(HERE, 'forms.json');
const DIC_PATH = path.join(path.dirname(require.resolve('kuromoji/package.json')), 'dict');

const SUFFIX = new Set([
  'て', 'で', 'た', 'だ', 'ない', 'ず', 'ぬ', 'う', 'よう',
  'ます', 'ません', 'ました', 'ませんでした',
  'ながら', 'たり', 'たら', 'なら', 'ば',
  'れる', 'られる', 'せる', 'させる', 'たい', 'たがる', 'そう',
  'ろ', 'よ', 'な', 'ちゃ', 'じゃ', 'ちゃう', 'じゃう',
  'てる', 'でる', 'とく', 'どく', 'ても', 'でも',
  'たって', 'だって', 'つつ', 'そうだ', 'そうに', 'そうな',
  'べき', 'まい', 'らしい', 'みたい', 'っきり'
]);

const AUX_VERBS = new Set([
  'ちゃう', 'じゃう', 'しまう', 'てる', 'でる', 'とく', 'どく',
  'おく', 'みる', 'いく', 'くる', 'いる', 'ある', 'やがる', 'がる'
]);

const U_DAN = new Set(['う', 'く', 'ぐ', 'す', 'ず', 'つ', 'ぬ', 'ぶ', 'む', 'る', 'づ']);
const isHira = ch => /[\u3040-\u309f]/.test(ch);
function isVerbLike(word) {
  const last = word.slice(-1);
  return isHira(last) && U_DAN.has(last);
}

function isAppendable(tok) {
  if ((tok.pos === '助動詞' || tok.pos === '助詞') && SUFFIX.has(tok.surface_form)) return true;
  if (tok.pos === '動詞' && AUX_VERBS.has(tok.basic_form)) return true;
  return false;
}

function extendEnd(toks, idx) {
  let j = idx + 1;
  while (j < toks.length && isAppendable(toks[j])) j++;
  return j;
}

function extract(textLines, songTitle, tokenizer, wordSet, phraseDict, formsByWord) {
  const add = (word, form) => {
    if (!form) return;
    if (!formsByWord[word]) formsByWord[word] = {};
    if (!formsByWord[word][form]) formsByWord[word][form] = new Set();
    formsByWord[word][form].add(songTitle);
  };

  for (const line of textLines) {
    const toks = tokenizer.tokenize(line);

    // 1) 普通动词：按 basic_form 精确匹配
    for (let i = 0; i < toks.length; i++) {
      const t = toks[i];
      if (!wordSet.has(t.basic_form) || t.pos !== '動詞' || !isVerbLike(t.basic_form)) continue;

      const cf = t.conjugated_form || '*';
      if (cf === '基本形' || cf === '命令ｅ' || cf === '命令ろ' || cf === '命令よ' || cf === '命令i') {
        add(t.basic_form, t.surface_form);
      }

      let form = t.surface_form;
      let appended = false;
      let j = i + 1;
      while (j < toks.length && isAppendable(toks[j])) {
        form += toks[j].surface_form;
        appended = true;
        j++;
      }
      if (appended) add(t.basic_form, form);
    }

    // 2) 惯用表达/短语：按 token 序列匹配整条短语
    for (const phrase of Object.keys(phraseDict)) {
      const seq = phraseDict[phrase];
      if (seq.length < 2) continue;
      for (let i = 0; i + seq.length <= toks.length; i++) {
        let ok = true;
        for (let k = 0; k < seq.length; k++) {
          const tokBasic = toks[i + k].basic_form || toks[i + k].surface_form;
          if (tokBasic !== seq[k]) { ok = false; break; }
        }
        if (!ok) continue;
        const end = extendEnd(toks, i + seq.length - 1);
        add(phrase, toks.slice(i, end).map(t => t.surface_form).join(''));
      }
    }
  }
}

function cleanForms(word, formSongs) {
  return Object.entries(formSongs)
    .filter(([f]) => !/(ちゃ|じゃ|ちゃい|じゃい)$/.test(f))
    .sort((a, b) => {
      if (a[0] === word) return -1;
      if (b[0] === word) return 1;
      return a[0].localeCompare(b[0], 'ja');
    })
    .map(([f, songs]) => [f, [...songs][0]]);
}

const vocab = JSON.parse(fs.readFileSync(VOCAB_PATH, 'utf8'));
const wordSet = new Set(vocab.map(w => w.word));

kuromoji.builder({ dicPath: DIC_PATH }).build((err, tokenizer) => {
  if (err) {
    console.error('kuromoji 初始化失败：', err);
    process.exit(1);
  }

  const phraseDict = {};
  for (const w of vocab) {
    const toks = tokenizer.tokenize(w.word);
    if (toks.length >= 2 && isVerbLike(w.word)) {
      phraseDict[w.word] = toks.map(t => t.basic_form || t.surface_form);
    }
  }

  const formsByWord = {};
  const files = fs.readdirSync(LYRICS_DIR).filter(f => f.endsWith('.md'));

  for (const file of files) {
    const md = fs.readFileSync(path.join(LYRICS_DIR, file), 'utf8');
    const titleMatch = md.match(/^title:\s*["']?([^"'\n]+?)["']?\s*$/m);
    const songTitle = titleMatch ? titleMatch[1].trim() : file.replace(/\.md$/, '');
    const section = md.split(/^## /m).find(s => s.startsWith('日文歌词'));
    if (!section) continue;
    const lines = section.split('\n').slice(1);
    const textLines = [];
    for (const line of lines) {
      if (/^## /.test(line)) break;
      if (line.trim() && !line.trim().startsWith('|')) textLines.push(line.trim());
    }
    extract(textLines, songTitle, tokenizer, wordSet, phraseDict, formsByWord);
  }

  const result = {};
  for (const word of Object.keys(formsByWord)) {
    const cleaned = cleanForms(word, formsByWord[word]);
    // 只有字典形就不写入了，页面不展示多余内容
    if (cleaned.length > 1 || (cleaned.length === 1 && cleaned[0][0] !== word)) {
      result[word] = Object.fromEntries(cleaned);
    }
  }

  fs.writeFileSync(OUT_PATH, JSON.stringify(result, null, 1), 'utf8');
  console.log('已生成 forms.json：' + Object.keys(result).length + ' 个词条');
});
