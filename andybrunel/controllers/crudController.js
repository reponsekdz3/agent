const db = require('../models/db');

function crudHandler(collection) {
  return async (req, res) => {
    const id = req.params.id;
    try {
      if (req.method === 'GET' && id) {
        const item = await db.getById(collection, id);
        if (!item) return res.status(404).json({ error: `${collection} not found` });
        return res.json(item);
      }
      if (req.method === 'GET') {
        const items = await db.getAll(collection);
        return res.json(items);
      }
      if (req.method === 'POST') {
        const item = await db.create(collection, req.body);
        return res.status(201).json(item);
      }
      if (req.method === 'PUT' || req.method === 'PATCH') {
        if (!id) return res.status(400).json({ error: 'ID required for update' });
        const item = await db.update(collection, id, req.body);
        if (!item) return res.status(404).json({ error: `${collection} not found` });
        return res.json(item);
      }
      if (req.method === 'DELETE') {
        if (!id) return res.status(400).json({ error: 'ID required for delete' });
        const ok = await db.remove(collection, id);
        if (!ok) return res.status(404).json({ error: `${collection} not found` });
        return res.status(204).send();
      }
      res.status(405).json({ error: 'Method not allowed' });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  };
}

module.exports = {
  customers: crudHandler('customer'),
  promotions: crudHandler('promotion'),
  promotionVehicles: crudHandler('promotion_vehicle'),
  users: crudHandler('users'),
  vehicles: crudHandler('vehicle'),
};
