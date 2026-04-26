// This library handles the heavy lifting of verifying the Google token
const { OAuth2Client } = require('google-auth-library');

// We initialize the client using your ID from the Vercel Environment Variables
const client = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

export default async function handler(req, res) {
    // 1. Only allow POST requests (since our frontend 'fetch' uses POST)
    if (req.method !== 'POST') {
        return res.status(405).json({ message: 'Method not allowed' });
    }

    // 2. Get the token that was sent in the 'body' of the fetch request
    const { token } = req.body;

    if (!token) {
        return res.status(400).json({ success: false, message: 'Token is missing' });
    }

    try {
        // 3. Ask Google: "Is this token actually valid for my Client ID?"
        const ticket = await client.verifyIdToken({
            idToken: token,
            audience: process.env.GOOGLE_CLIENT_ID,
        });

        // 4. Extract the user information from the verified token
        const payload = ticket.getPayload();
        
        // This is the 'data' that gets sent back to your 'login.html'
        const user = {
            id: payload.sub, // Unique Google ID
            email: payload.email,
            name: payload.name,
            picture: payload.picture
        };

        // 5. Send the success response
        return res.status(200).json({ 
            success: true, 
            user: user 
        });

    } catch (error) {
        // If the token was fake, expired, or edited, this code runs
        console.error("Verification error:", error);
        return res.status(401).json({ 
            success: false, 
            message: "Invalid or expired token" 
        });
    }
}