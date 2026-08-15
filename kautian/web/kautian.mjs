/**
 * kautian.mjs — turn a KTWEB1 document into rows.
 *
 * Zero dependencies, no build step, no WASM. Fetch the document with
 * `Content-Encoding: br` and the browser has already done the decompression by
 * the time `response.json()` resolves; this file only undoes the modelling —
 * the derived columns and the romanisation ranks that `kautian/opt/webjson.py`
 * removed.
 *
 *   const doc = await (await fetch("/kautian.web.json")).json();
 *   const { 詞目, 例句 } = decode(doc);
 *   詞目[0].漢字;
 *
 * One forward pass, in document order. A derived column reads only columns
 * earlier in its own table plus tables decoded before it, which is what makes a
 * single pass enough — and it is required, not incidental: a `tailo` column is
 * decoded against a 漢字 column that is itself derived.
 *
 * Everything here is pinned against the Python encoder by
 * `kautian/tests/test_web_json.py`, which decodes the real document with this
 * file and compares all 746,857 values against the canonical output.
 */

const FORMAT = "KTWEB1";
const UNIT = "\u001f";
const PAIR = "\u0000";
const ESCAPE_RANK = 255;
const NULL = 2;
const ALIGNED = 1;

const HAN = /[\u3400-\u9fff\u{20000}-\u{2ffff}]/u;

/** Render a value the way Python's f-string did when the rules were applied. */
const asText = (value) => (value === null || value === undefined ? "None" : String(value));

const indexBy = (table, keyColumn, valueColumn) => {
  const keys = table[keyColumn];
  const values = table[valueColumn];
  const lookup = new Map();
  for (let index = 0; index < keys.length; index += 1) lookup.set(keys[index], values[index]);
  return lookup;
};

/** 例句順序 restarts at 1 for every (詞目id, 義項id) run in table order. */
const exampleOrder = (_context, rows) => {
  const words = rows["詞目id"];
  const senses = rows["義項id"];
  const orders = [];
  let previousWord = null;
  let previousSense = null;
  let counter = 0;
  for (let index = 0; index < words.length; index += 1) {
    const same = words[index] === previousWord && senses[index] === previousSense;
    counter = same ? counter + 1 : 1;
    previousWord = words[index];
    previousSense = senses[index];
    orders.push(counter);
  }
  return orders;
};

const RULES = {
  headword_hanji: (context, rows, idColumn) => {
    const hanji = indexBy(context["詞目"], "詞目id", "漢字");
    return rows[idColumn].map((id) => (hanji.has(id) ? hanji.get(id) : null));
  },

  sense_gloss: (context, rows, idColumn) => {
    const gloss = indexBy(context["義項"], "義項id", "解說");
    return rows[idColumn].map((id) => (gloss.has(id) ? gloss.get(id) : null));
  },

  sense_headword_hanji: (context, rows, idColumn) => {
    const owner = indexBy(context["義項"], "義項id", "詞目id");
    const hanji = indexBy(context["詞目"], "詞目id", "漢字");
    return rows[idColumn].map((id) => {
      const word = owner.has(id) ? owner.get(id) : undefined;
      return hanji.has(word) ? hanji.get(word) : null;
    });
  },

  headword_audio: (_context, rows, idColumn) => rows[idColumn].map((id) => `${asText(id)}(1)`),

  example_order: exampleOrder,

  /** 音檔檔名 is {詞目id}-{position of 義項id within the word}-{例句順序}. */
  example_audio: (context, rows) => {
    const positions = new Map();
    const seen = new Map();
    const words = context["義項"]["詞目id"];
    const senses = context["義項"]["義項id"];
    for (let index = 0; index < words.length; index += 1) {
      if (!seen.has(words[index])) seen.set(words[index], new Set());
      const forWord = seen.get(words[index]);
      if (!forWord.has(senses[index])) {
        forWord.add(senses[index]);
        positions.set(`${words[index]}${PAIR}${senses[index]}`, forWord.size);
      }
    }
    const orders = exampleOrder(context, rows);
    return rows["詞目id"].map((word, index) => {
      const key = `${word}${PAIR}${rows["義項id"][index]}`;
      return `${asText(word)}-${asText(positions.get(key))}-${orders[index]}`;
    });
  },
};

/**
 * Expand an enumerated column.
 *
 * Every row of a given value gets the *same* string, not a copy of it, which is
 * the point: 詞目.分類 becomes 29,591 pointers into a table of 106 strings.
 */
const decodeEnum = (spec) => {
  const { enum: values, at } = spec;
  const out = new Array(at.length);
  for (let index = 0; index < at.length; index += 1) out[index] = values[at[index]];
  return out;
};

const decodeDerived = (spec, context, rows) => {
  const values = RULES[spec.rule](context, rows, ...spec.args);
  for (let index = 0; index < spec.at.length; index += 1) values[spec.at[index]] = spec.is[index];
  return values;
};

const decodeTailo = (spec, model, hanjiValues) => {
  const { aligned, ranks, escapes, caps, separators, literals } = spec;
  const out = [];
  let rankAt = 0;
  let escapeAt = 0;
  let separatorAt = 0;
  let literalAt = 0;
  for (let index = 0; index < aligned.length; index += 1) {
    if (aligned[index] === NULL) {
      out.push(null);
      continue;
    }
    if (aligned[index] !== ALIGNED) {
      out.push(literals[literalAt]);
      literalAt += 1;
      continue;
    }
    const syllables = [];
    for (const character of hanjiValues[index] ?? "") {
      if (!HAN.test(character)) continue;
      const rank = ranks[rankAt];
      let syllable = rank === ESCAPE_RANK ? escapes[escapeAt] : model[character][rank];
      if (rank === ESCAPE_RANK) escapeAt += 1;
      if (caps[rankAt]) syllable = syllable.charAt(0).toUpperCase() + syllable.slice(1);
      rankAt += 1;
      syllables.push(syllable);
    }
    const gaps = separators[separatorAt].split(UNIT);
    separatorAt += 1;
    let text = gaps[0];
    for (let at = 0; at < syllables.length; at += 1) text += syllables[at] + gaps[at + 1];
    out.push(text);
  }
  return out;
};

/** Tables the derived rules join against, so they are decoded even if unwanted. */
const CONTEXT_TABLES = ["詞目", "義項"];

/**
 * Decode a KTWEB1 document to `{ tableName: { column: [value, ...] } }`.
 *
 * The columnar form is the cheap one to hold: one array per column instead of
 * one object per row. Prefer it for anything long-lived, and use `rows()` to
 * shape the handful of records a view actually renders.
 *
 * `only` limits the work to the tables named, plus the two the derived rules
 * join against — a rule reads 詞目 and 義項, so those are decoded whether or not
 * they were asked for, and dropped from the result if they were not.
 *
 * `context` supplies tables decoded earlier, which is what lets a document be
 * loaded and released a table at a time: hold 詞目 and 義項, and every other
 * table can be decoded from a document containing only itself. Peak memory then
 * tracks the largest single table rather than the whole dictionary.
 */
export function decodeColumns(document, { only, context: prior } = {}) {
  if (document?.format !== FORMAT) throw new Error(`not a ${FORMAT} document`);
  const context = { ...prior };
  const needed = CONTEXT_TABLES.filter((name) => !(name in context));
  const wanted = only && new Set([...only, ...needed]);
  for (const entry of document.tables) {
    if (wanted && !wanted.has(entry.name)) continue;
    const columns = {};
    for (const column of entry.columns) {
      const spec = entry.values[column];
      if (Array.isArray(spec)) columns[column] = spec;
      else if (spec.enum) columns[column] = decodeEnum(spec);
      else if (spec.rule) columns[column] = decodeDerived(spec, context, columns);
      else columns[column] = decodeTailo(spec, document.model, columns[spec.tailo]);
    }
    context[entry.name] = columns;
  }
  if (only) {
    for (const name of needed) if (!only.includes(name)) delete context[name];
  }
  return context;
}

/**
 * Materialise row objects from one decoded table.
 *
 * `rows(tables.詞目)` builds every row; `rows(tables.詞目, 0, 20)` builds a page.
 * Row objects cost roughly a third again of what the columns cost, so building
 * them for the whole dictionary is a choice, not a requirement.
 */
export function rows(columns, start = 0, end) {
  const names = Object.keys(columns);
  const last = end ?? columns[names[0]].length;
  const out = new Array(Math.max(0, last - start));
  for (let index = start; index < last; index += 1) {
    const row = {};
    for (const name of names) row[name] = columns[name][index];
    out[index - start] = row;
  }
  return out;
}

/** Decode straight to `{ tableName: [rowObject, ...] }`. Convenience over economy. */
export function decode(document, options) {
  const columns = decodeColumns(document, options);
  const tables = {};
  for (const name of Object.keys(columns)) tables[name] = rows(columns[name]);
  return tables;
}

export default decode;
