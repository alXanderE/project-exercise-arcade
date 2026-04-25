import dotenv from "dotenv";
import { connectToDatabase } from "./db.js";
import { createApp } from "./app.js";

dotenv.config();

const host = process.env.HOST || "0.0.0.0";
const port = Number(process.env.PORT || 3000);
const mongoUri = process.env.MONGODB_URI;

async function start() {
  await connectToDatabase(mongoUri);

  const app = createApp();

  app.listen(port, host, () => {
    console.log(`Server listening on http://${host}:${port}`);
  });
}

start().catch((error) => {
  console.error("Failed to start server:", error);
  process.exit(1);
});
