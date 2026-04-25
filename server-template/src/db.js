import mongoose from "mongoose";

export async function connectToDatabase(uri) {
  if (!uri) {
    throw new Error("MONGODB_URI is required.");
  }

  await mongoose.connect(uri);
}
