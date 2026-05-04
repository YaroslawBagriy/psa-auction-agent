import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const { Presentation, PresentationFile } = await import("@oai/artifact-tool");

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const outPath = path.join(__dirname, "psa-pokemon-auction-agent-final-presentation.pptx");
const previewDir = path.resolve(repoRoot, "tmp/slides/final-presentation/previews");
await fs.mkdir(previewDir, { recursive: true });

async function readImageBlob(relativePath) {
  const bytes = await fs.readFile(path.resolve(repoRoot, relativePath));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

const IMG = {
  vault: "latex-final-images/psa-vault-listing.png",
  early: "latex-final-images/early-garchomp-output.png",
  garchomp: "latex-final-images/garchomp-market-context-output.png",
  pikachu: "latex-final-images/high-value-pikachu-output.png",
  outlier: "latex-final-images/outlier-charizard-output.png",
};

const C = {
  bg: "#07111F",
  bg2: "#0D1B2E",
  card: "#10243A",
  card2: "#162D49",
  red: "#E31B23",
  gold: "#F4B942",
  green: "#35D07F",
  cyan: "#65D7FF",
  blue: "#4E8FFF",
  white: "#F7FAFC",
  muted: "#B8C6D9",
  ink: "#111827",
};

const FONT = {
  title: "Poppins",
  body: "Lato",
  mono: "Inconsolata",
};

const presentation = Presentation.create({
  slideSize: { width: 1280, height: 720 },
});

presentation.theme.colorScheme = {
  name: "PSA Auction Agent",
  themeColors: {
    accent1: C.red,
    accent2: C.gold,
    accent3: C.green,
    accent4: C.cyan,
    bg1: C.bg,
    bg2: C.bg2,
    tx1: C.white,
    tx2: C.muted,
  },
};

function addBg(slide) {
  slide.background.fill = C.bg;
  slide.shapes.add({
    geometry: "rect",
    position: { left: 0, top: 0, width: 1280, height: 720 },
    fill: {
      type: "gradient",
      angle: 0,
      stops: [
        { offset: 0, color: C.bg },
        { offset: 72000, color: C.bg2 },
        { offset: 100000, color: "#111827" },
      ],
    },
    line: { width: 0, fill: C.bg },
  });
  slide.shapes.add({
    geometry: "ellipse",
    position: { left: 980, top: -180, width: 470, height: 470 },
    fill: "#E31B2333",
    line: { width: 0, fill: "#E31B2300" },
  });
  slide.shapes.add({
    geometry: "ellipse",
    position: { left: -160, top: 500, width: 380, height: 380 },
    fill: "#65D7FF22",
    line: { width: 0, fill: "#65D7FF00" },
  });
}

function addTitle(slide, text, subtitle = "") {
  const title = slide.shapes.add({
    geometry: "rect",
    position: { left: 56, top: 38, width: 850, height: 60 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  title.text = text;
  title.text.typeface = FONT.title;
  title.text.fontSize = 34;
  title.text.bold = true;
  title.text.color = C.white;
  title.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };

  if (subtitle) {
    const sub = slide.shapes.add({
      geometry: "rect",
      position: { left: 58, top: 90, width: 760, height: 36 },
      fill: "#00000000",
      line: { width: 0, fill: "#00000000" },
    });
    sub.text = subtitle;
    sub.text.typeface = FONT.body;
    sub.text.fontSize = 17;
    sub.text.color = C.muted;
    sub.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  }
}

function addPill(slide, text, x, y, w, color = C.red) {
  const pill = slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: 34 },
    adjustmentList: [{ name: "adj", formula: "val 50000" }],
    fill: `${color}22`,
    line: { width: 1.2, fill: color },
  });
  pill.text = text;
  pill.text.typeface = FONT.body;
  pill.text.fontSize = 14;
  pill.text.bold = true;
  pill.text.color = color;
  pill.text.alignment = "center";
  pill.text.verticalAlignment = "middle";
  pill.text.insets = { left: 8, right: 8, top: 3, bottom: 3 };
  return pill;
}

function addBullet(slide, text, x, y, w, h, color = C.white, size = 22) {
  const shape = slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  shape.text = text;
  shape.text.typeface = FONT.body;
  shape.text.fontSize = size;
  shape.text.color = color;
  shape.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  return shape;
}

function addMetric(slide, label, value, x, y, w, accent = C.cyan) {
  const box = slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: 104 },
    adjustmentList: [{ name: "adj", formula: "val 18000" }],
    fill: C.card,
    line: { width: 1, fill: "#FFFFFF22" },
  });
  const v = slide.shapes.add({
    geometry: "rect",
    position: { left: x + 18, top: y + 16, width: w - 36, height: 42 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  v.text = value;
  v.text.typeface = FONT.title;
  v.text.fontSize = 30;
  v.text.bold = true;
  v.text.color = accent;
  v.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  const l = slide.shapes.add({
    geometry: "rect",
    position: { left: x + 18, top: y + 62, width: w - 36, height: 30 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  l.text = label;
  l.text.typeface = FONT.body;
  l.text.fontSize = 13;
  l.text.color = C.muted;
  l.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  return box;
}

function addCard(slide, x, y, w, h, title, body, accent = C.red) {
  const card = slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: h },
    adjustmentList: [{ name: "adj", formula: "val 11000" }],
    fill: C.card,
    line: { width: 1, fill: "#FFFFFF24" },
  });
  slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: 7, height: h },
    fill: accent,
    line: { width: 0, fill: accent },
  });
  const head = slide.shapes.add({
    geometry: "rect",
    position: { left: x + 22, top: y + 18, width: w - 44, height: 30 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  head.text = title;
  head.text.typeface = FONT.title;
  head.text.fontSize = 18;
  head.text.bold = true;
  head.text.color = C.white;
  head.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  const text = slide.shapes.add({
    geometry: "rect",
    position: { left: x + 22, top: y + 56, width: w - 44, height: h - 70 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  text.text = body;
  text.text.typeface = FONT.body;
  text.text.fontSize = 16;
  text.text.color = C.muted;
  text.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  return card;
}

async function addImage(slide, relPath, x, y, w, h, fit = "cover", alt = "") {
  const img = slide.images.add({
    blob: await readImageBlob(relPath),
    fit,
    alt,
  });
  img.position = { left: x, top: y, width: w, height: h };
  img.geometry = "roundRect";
  return img;
}

function addFooter(slide, n) {
  const foot = slide.shapes.add({
    geometry: "rect",
    position: { left: 56, top: 675, width: 1168, height: 24 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  foot.text = `PSA Pokemon Auction Agent  ·  ${n}/7`;
  foot.text.typeface = FONT.body;
  foot.text.fontSize = 12;
  foot.text.color = "#FFFFFF77";
  foot.text.alignment = "right";
  foot.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
}

// Slide 1
{
  const slide = presentation.slides.add();
  addBg(slide);
  await addImage(slide, IMG.vault, 618, 72, 600, 560, "cover", "PSA Vault eBay listing screenshot");
  slide.shapes.add({
    geometry: "rect",
    position: { left: 610, top: 72, width: 620, height: 560 },
    fill: "#07111F44",
    line: { width: 0, fill: "#00000000" },
  });
  const title = slide.shapes.add({
    geometry: "rect",
    position: { left: 58, top: 92, width: 550, height: 190 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  title.text = "PSA Pokemon\nAuction Agent";
  title.text.typeface = FONT.title;
  title.text.fontSize = 52;
  title.text.bold = true;
  title.text.color = C.white;
  title.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  addBullet(slide, "Final project: a multi-agent LLM system that scans PSA eBay auctions, researches sold comps, and recommends safe manual bids.", 62, 306, 500, 96, C.muted, 22);
  addPill(slide, "LangChain agents", 62, 432, 170, C.cyan);
  addPill(slide, "eBay data", 250, 432, 120, C.gold);
  addPill(slide, "Manual bidding", 388, 432, 150, C.green);
  addMetric(slide, "Passing automated tests", "66", 62, 520, 150, C.green);
  addMetric(slide, "Presentation length", "5 min", 232, 520, 160, C.gold);
  addMetric(slide, "Default bid mode", "manual", 412, 520, 180, C.cyan);
  slide.speakerNotes.setText("Open by answering the first question directly: my project is a PSA Pokemon auction agent. I built a multi-agent system that reviews listings, researches market value, and recommends manual bids.");
  addFooter(slide, 1);
}

// Slide 2
{
  const slide = presentation.slides.add();
  addBg(slide);
  addTitle(slide, "What was the project? What did I do?", "I built the first working MVP of a safe auction-analysis assistant.");
  await addImage(slide, IMG.early, 684, 92, 512, 400, "cover", "Early terminal recommendation output");
  addCard(slide, 60, 154, 262, 160, "I built", "Python + LangChain app\nTyped Pydantic models\nSQLite logging/storage", C.cyan);
  addCard(slide, 352, 154, 262, 160, "It reviews", "PSA official auctions\nPokemon allow-list\nPSA grade + Vault signals", C.gold);
  addCard(slide, 60, 344, 262, 160, "It analyzes", "eBay sold comps\nSell-through rate\nTrend + risk flags", C.green);
  addCard(slide, 352, 344, 262, 160, "It outputs", "Manual bid recommendation\nor exact denial reason\nNo website automation", C.red);
  addBullet(slide, "Core question: “Can this card be bought low enough to leave resale margin?”", 74, 556, 1080, 44, C.white, 24);
  slide.speakerNotes.setText("This slide explicitly answers what the project was and what I did. I built a working MVP, not just a proposal.");
  addFooter(slide, 2);
}

// Slide 3
{
  const slide = presentation.slides.add();
  addBg(slide);
  addTitle(slide, "Why I chose this topic", "It connected a real workflow I care about to the class theme: agentic LLM systems.");
  await addImage(slide, IMG.vault, 640, 96, 520, 390, "cover", "PSA Vault listing screenshot");
  addCard(slide, 66, 146, 500, 104, "Personal motivation", "I buy and sell Pokemon cards, so auction evaluation is a real repeated decision for me.", C.green);
  addCard(slide, 66, 276, 500, 104, "Good LLM fit", "The hard part is messy judgment: card identity, language, comps, outliers, trend, and risk.", C.cyan);
  addCard(slide, 66, 406, 500, 104, "Good systems fit", "It forced me to combine prompts, tools, APIs, typed data, logging, and guardrails.", C.gold);
  addPill(slide, "Real stakes", 650, 514, 120, C.red);
  addPill(slide, "Noisy data", 786, 514, 120, C.gold);
  addPill(slide, "Agent workflow", 922, 514, 150, C.cyan);
  addBullet(slide, "Minimal goal: safe recommendations. Optimistic goal: production-minded multi-agent architecture.", 92, 570, 980, 48, C.white, 23);
  slide.speakerNotes.setText("This answers why I chose the topic: it was personally useful, technically interesting, and a good match for class concepts.");
  addFooter(slide, 3);
}

// Slide 4
{
  const slide = presentation.slides.add();
  addBg(slide);
  addTitle(slide, "How I applied class topics + feedback", "Prompt agents do judgment; deterministic Python applies the brakes.");
  const xs = [70, 248, 426, 604, 782, 960];
  const labels = [
    ["Scanner", "Fetch PSA auctions"],
    ["Validation", "Scope + parsing"],
    ["Listing Agent", "Worth researching?"],
    ["Market Agent", "Sold comps + STR"],
    ["Analysis Agent", "Fair value + max bid"],
    ["Bid Tool", "Manual action"],
  ];
  for (let i = 0; i < labels.length; i++) {
    addCard(slide, xs[i], 180, 150, 142, labels[i][0], labels[i][1], [C.cyan, C.gold, C.green, C.blue, C.red, C.green][i]);
    if (i < labels.length - 1) {
      slide.shapes.add({
        geometry: "rightArrow",
        position: { left: xs[i] + 132, top: 226, width: 58, height: 38 },
        fill: "#FFFFFF35",
        line: { width: 0, fill: "#FFFFFF00" },
      });
    }
  }
  await addImage(slide, IMG.garchomp, 78, 382, 510, 220, "cover", "Structured reviewed auction output");
  await addImage(slide, IMG.pikachu, 628, 382, 510, 220, "cover", "High-value reviewed auction output");
  addPill(slide, "LangChain prompt agents", 75, 336, 210, C.cyan);
  addPill(slide, "Deterministic guardrails", 306, 336, 220, C.red);
  addPill(slide, "Structured outputs", 548, 336, 180, C.green);
  addCard(slide, 764, 322, 360, 96, "Class concepts", "agents, tool use, structured output, one-shot prompting, evaluation", C.cyan);
  addCard(slide, 764, 442, 360, 96, "Classmate feedback", "track sell-through rate and handle Japanese vs. English cards separately", C.gold);
  slide.speakerNotes.setText("This slide explicitly maps the implementation to class topics and classmate feedback. Dante's feedback about Japanese cards led to language detection and language-aware comp matching.");
  addFooter(slide, 4);
}

// Slide 5
{
  const slide = presentation.slides.add();
  addBg(slide);
  addTitle(slide, "What the workflow looks like live", "Each auction gets reviewed immediately, with an explicit reason.");
  await addImage(slide, IMG.vault, 52, 150, 510, 420, "cover", "PSA Vault listing screenshot");
  const terminal = slide.shapes.add({
    geometry: "roundRect",
    position: { left: 608, top: 146, width: 590, height: 430 },
    adjustmentList: [{ name: "adj", formula: "val 11000" }],
    fill: "#020617",
    line: { width: 1, fill: "#FFFFFF22" },
  });
  const text = slide.shapes.add({
    geometry: "rect",
    position: { left: 634, top: 172, width: 538, height: 376 },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  text.text = "------ Start auction 1/100 ------\nStep 1: Checking requirements\nStep 2: Listing-review agent\nStep 3: Market research\nStep 4: Analysis agent\nStep 5: Bid safety rules\n\nFinal decision: DENIED\nReason: max bid below current price\n------ End auction 1/100 ------";
  text.text.typeface = FONT.mono;
  text.text.fontSize = 25;
  text.text.color = "#D8F3DC";
  text.text.insets = { left: 0, right: 0, top: 0, bottom: 0 };
  addPill(slide, "PSA Vault signal appears on page", 70, 590, 270, C.gold);
  addPill(slide, "Title alone was not enough", 360, 590, 230, C.red);
  slide.speakerNotes.setText("This is the operational demo slide. It shows how the system reviews one listing, logs the steps, and gives a denial or acceptance reason.");
  addFooter(slide, 5);
}

// Slide 6
{
  const slide = presentation.slides.add();
  addBg(slide);
  addTitle(slide, "Challenges: noisy comps, API limits, safety", "The hard part was not writing code; it was making the decisions trustworthy.");
  await addImage(slide, IMG.outlier, 54, 136, 548, 384, "cover", "Outlier Charizard overvaluation output");
  addCard(slide, 640, 134, 500, 96, "Challenge 1: bad comps", "Broad searches mixed $27-$30 sales with $500-$1000 outliers.", C.red);
  addCard(slide, 640, 248, 500, 96, "How I handled it", "Added one-shot prompting + lower-sold-comp guardrails.", C.green);
  addCard(slide, 640, 362, 500, 96, "Challenge 2: eBay API limits", "Official proxy bidding needs approval, so MVP defaults to manual bidding.", C.gold);
  addCard(slide, 640, 476, 500, 96, "With more time", "Build labeled evaluation data and use more reliable official sold-comp sources.", C.cyan);
  addBullet(slide, "Lesson: letting the LLM analyze does not mean letting the LLM have the final word.", 90, 590, 1040, 48, C.white, 25);
  slide.speakerNotes.setText("This slide answers the challenges question: noisy evidence, official API limits, and safety. It also explains what I learned and what I would do with more time.");
  addFooter(slide, 6);
}

// Slide 7
{
  const slide = presentation.slides.add();
  addBg(slide);
  addTitle(slide, "Takeaway: agentic systems need judgment and brakes", "What worked, what I learned, and where I would go next.");
  addCard(slide, 70, 132, 500, 116, "What worked", "The app scans, filters, researches, explains, and produces manual auction recommendations.", C.green);
  addCard(slide, 70, 276, 500, 116, "What I learned", "LLMs are useful analysts, but they need schemas, tools, logs, tests, and deterministic safety checks.", C.cyan);
  addCard(slide, 70, 420, 500, 116, "Next step", "Create a labeled benchmark of real listings and measure false-positive bid recommendations.", C.gold);
  await addImage(slide, IMG.pikachu, 642, 138, 516, 236, "cover", "High-value Pikachu output");
  await addImage(slide, IMG.vault, 642, 402, 516, 184, "cover", "PSA Vault listing evidence");
  addPill(slide, "Works: scans + explains + recommends", 72, 585, 300, C.green);
  addPill(slide, "Limit: market comps still noisy", 392, 585, 260, C.gold);
  addPill(slide, "Default: human places bid", 672, 585, 250, C.cyan);
  slide.speakerNotes.setText("Close by restating the thesis and the next step. The project advanced my knowledge from using LLMs as chatbots to designing LLMs as components in a guarded system.");
  addFooter(slide, 7);
}

for (let i = 0; i < presentation.slides.count; i++) {
  const slide = presentation.slides.getItem(i);
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(
    path.join(previewDir, `slide-${String(i + 1).padStart(2, "0")}.png`),
    Buffer.from(await png.arrayBuffer()),
  );
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outPath);
console.log(outPath);
