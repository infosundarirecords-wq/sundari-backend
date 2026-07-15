# Sundari AI Mix Engineer — Aapke liye 3 Simple Steps

Ye ek-baar ka setup hai. Iske baad terminal kabhi dobara nahi kholna padega.

## Step 1: Zip file download karke unzip karein
Is poore folder ko apne Mac par kisi jagah rakh dein (jaise Documents folder mein).

## Step 2: Terminal mein ye 2 lines chalayein (SIRF EK BAAR)

Terminal kholein (Applications > Utilities > Terminal), aur ye type karein
(jahan aapne folder rakha hai wahan `cd` karke):

```
cd Documents/sundari-ai-mix-engineer/install
bash setup_once.sh
```

Enter dabayein. Ye khud hi sab kuch karega:
- Python packages install karega
- Backend ko hamesha auto-start banayega
- Confirm karega ke sab sahi chal raha hai

Isme 3-5 minute lag sakte hain (packages download hone mein). Jab
"SETUP COMPLETE!" dikhe, samajh lein ho gaya.

## Step 3: Plugin build karna (Logic Pro ke liye)

`plugin/docs/BUILD_INSTRUCTIONS_MAC.md` file kholein aur usme diye steps
follow karein — ye plugin ko Logic Pro ke andar install karta hai
(AU format mein). Agar isme koi dikkat aaye, screenshot bhejein, main
madad karunga.

## Uske baad — hamesha ke liye

- Mac on karein → backend khud chalu ho jayega (background mein, silently)
- Logic Pro kholein → Sundari plugin kisi bhi channel par load karein
- Role select karein → Analyze dabayein → AI Teacher Panel mein jawab
  aayega
- **Terminal kabhi dobara nahi kholna padega.**

## Security reminder

Aapne jo API key screenshot mein share ki thi, wo ab is `.env` file
mein set hai. Chunki wo photo mein poori dikh gayi thi, salah di jaati
hai ki setup complete hone ke baad aap **console.anthropic.com** mein
jaakar wo purani key delete karke ek nayi bana lein, aur `.env` file
mein sirf naya wala daal dein (backend/.env file ko text editor mein
kholkar `ANTHROPIC_API_KEY=` ke aage nayi key paste kar dein, phir
`bash setup_once.sh` dobara chala dein taaki naya key load ho jaaye).
