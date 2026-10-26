const express = require('express');
const ctrl = require('../controllers/crudController');
const router = express.Router();

const collections = ['customers', 'promotions', 'promotionVehicles', 'users', 'vehicles'];

collections.forEach(name => {
  router.get(`/${name}`, ctrl[name]);
  router.post(`/${name}`, ctrl[name]);
  router.get(`/${name}/:id`, ctrl[name]);
  router.put(`/${name}/:id`, ctrl[name]);
  router.patch(`/${name}/:id`, ctrl[name]);
  router.delete(`/${name}/:id`, ctrl[name]);
});

module.exports = router;
