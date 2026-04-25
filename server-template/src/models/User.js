import mongoose from "mongoose";

const userSchema = new mongoose.Schema(
  {
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true
    },
    displayName: {
      type: String,
      required: true,
      trim: true
    },
    passwordHash: {
      type: String,
      required: true
    },
    sessionToken: {
      type: String,
      default: null,
      index: true
    },
    sessionExpiresAt: {
      type: Date,
      default: null
    }
  },
  { timestamps: true }
);

export const User = mongoose.model("User", userSchema);
