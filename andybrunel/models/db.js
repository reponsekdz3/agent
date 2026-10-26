const fs = require('fs').promises;
const path = require('path');

const DB_PATH = path.join(__dirname, 'data', 'db.json');

async function ensureDb() {
  try {
    await fs.access(DB_PATH);
  } catch {
    await fs.mkdir(path.join(__dirname, 'data'), { recursive: true });
    await fs.writeFile(DB_PATH, JSON.stringify({ customer: [], promotion: [], promotion_vehicle: [], users: [], vehicle: [] }, null, 2));
  }
}

async function readDb() {
  await ensureDb();
  const data = await fs.readFile(DB_PATH, 'utf-8');
  return JSON.parse(data);
}

async function writeDb(data) {
  await ensureDb();
  await fs.writeFile(DB_PATH, JSON.stringify(data, null, 2));
}

async function getAll(collection) {
  const db = await readDb();
  return db[collection];
}

async function getById(collection, id) {
  const items = await getAll(collection);
  return items.find(item => item.id === id) || null;
}

async function create(collection, item) {
  const db = await readDb();
  const newItem = { ...item, id: item.id || require('crypto').randomUUID() };
  db[collection].push(newItem);
  await writeDb(db);
  return newItem;
}

async function update(collection, id, updates) {
  const db = await readDb();
  const index = db[collection].findIndex(item => item.id === id);
  if (index === -1) return null;
  db[collection][index] = { ...db[collection][index], ...updates, id: id };
  await writeDb(db);
  return db[collection][index];
}

async function remove(collection, id) {
  const db = await readDb();
  const index = db[collection].findIndex(item => item.id === id);
  if (index === -1) return false;
  db[collection].splice(index, 1);
  await writeDb(db);
  return true;
}

module.exports = { getAll, getById, create, update, remove };
