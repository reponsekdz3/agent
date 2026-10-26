const express = require('express');
const routes = require('./routes');
const app = express();

app.use(express.json());
app.use('/api', routes);
app.use((req, res) => res.status(404).json({ error: 'Not found' }));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
