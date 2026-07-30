export interface NicheNode {
  id: string
  label: string
  children?: NicheNode[]
}

export const NICHE_TAXONOMY: NicheNode[] = [
  {
    id: 'dining',
    label: 'Dining',
    children: [
      {
        id: 'dining-fine',
        label: 'Fine Dining',
        children: [
          { id: 'dining-fine-continental', label: 'Continental' },
          { id: 'dining-fine-asian', label: 'Asian Fusion' },
          { id: 'dining-fine-indian', label: 'Indian' },
          { id: 'dining-fine-mediterranean', label: 'Mediterranean' },
        ],
      },
      {
        id: 'dining-casual',
        label: 'Casual Dining',
        children: [
          { id: 'dining-casual-family', label: 'Family Style' },
          { id: 'dining-casual-bistro', label: 'Bistro' },
          { id: 'dining-casual-american', label: 'American' },
        ],
      },
      {
        id: 'dining-cafe',
        label: 'Café',
        children: [
          { id: 'dining-cafe-specialty', label: 'Specialty Coffee' },
          { id: 'dining-cafe-dessert', label: 'Dessert Café' },
          { id: 'dining-cafe-brunch', label: 'Brunch Spot' },
        ],
      },
      {
        id: 'dining-fastfood',
        label: 'Fast Food',
        children: [
          { id: 'dining-fastfood-burger', label: 'Burgers' },
          { id: 'dining-fastfood-pizza', label: 'Pizza' },
          { id: 'dining-fastfood-wraps', label: 'Wraps & Rolls' },
          { id: 'dining-fastfood-chinese', label: 'Chinese' },
        ],
      },
      { id: 'dining-bar', label: 'Bar & Lounge', children: [
        { id: 'dining-bar-cocktail', label: 'Cocktail Bar' },
        { id: 'dining-bar-sports', label: 'Sports Bar' },
        { id: 'dining-bar-rooftop', label: 'Rooftop Bar' },
      ]},
      { id: 'dining-bakery', label: 'Bakery & Patisserie', children: [
        { id: 'dining-bakery-artisan', label: 'Artisan Bread' },
        { id: 'dining-bakery-cakes', label: 'Custom Cakes' },
        { id: 'dining-bakery-pastry', label: 'Pastry' },
      ]},
      { id: 'dining-cloud', label: 'Cloud Kitchen', children: [
        { id: 'dining-cloud-tiffin', label: 'Tiffin Service' },
        { id: 'dining-cloud-meals', label: 'Meal Preps' },
      ]},
      { id: 'dining-streetfood', label: 'Street Food', children: [
        { id: 'dining-streetfood-chaat', label: 'Chaat' },
        { id: 'dining-streetfood-dosa', label: 'Dosa & South Indian' },
        { id: 'dining-streetfood-grill', label: 'Grills & Kebabs' },
      ]},
    ],
  },
  {
    id: 'fashion',
    label: 'Fashion',
    children: [
      {
        id: 'fashion-tailoring',
        label: 'Tailoring',
        children: [
          { id: 'fashion-tailoring-mens', label: "Men's Tailoring" },
          { id: 'fashion-tailoring-womens', label: "Women's Tailoring" },
          { id: 'fashion-tailoring-bridal', label: 'Bridal Wear' },
          { id: 'fashion-tailoring-alterations', label: 'Alterations' },
        ],
      },
      {
        id: 'fashion-retail',
        label: 'Retail',
        children: [
          { id: 'fashion-retail-ethnic', label: 'Ethnic Wear' },
          { id: 'fashion-retail-western', label: 'Western Wear' },
          { id: 'fashion-retail-kids', label: "Kids' Fashion" },
          { id: 'fashion-retail-streetwear', label: 'Streetwear' },
          { id: 'fashion-retail-luxury', label: 'Luxury' },
        ],
      },
      {
        id: 'fashion-rental',
        label: 'Rental',
        children: [
          { id: 'fashion-rental-occasion', label: 'Occasion Wear' },
          { id: 'fashion-rental-costume', label: 'Costumes' },
          { id: 'fashion-rental-designer', label: 'Designer Rental' },
        ],
      },
      { id: 'fashion-accessories', label: 'Accessories', children: [
        { id: 'fashion-accessories-bags', label: 'Bags & Handbags' },
        { id: 'fashion-accessories-jewellery', label: 'Jewellery' },
        { id: 'fashion-accessories-footwear', label: 'Footwear' },
        { id: 'fashion-accessories-watches', label: 'Watches' },
      ]},
      { id: 'fashion-designer', label: 'Designer Studio', children: [
        { id: 'fashion-designer-couture', label: 'Couture' },
        { id: 'fashion-designer-ready', label: 'Ready-to-Wear' },
      ]},
    ],
  },
  {
    id: 'wellness',
    label: 'Wellness',
    children: [
      {
        id: 'wellness-spa',
        label: 'Spa & Massage',
        children: [
          { id: 'wellness-spa-thai', label: 'Thai Massage' },
          { id: 'wellness-spa-deep', label: 'Deep Tissue' },
          { id: 'wellness-spa-aromatherapy', label: 'Aromatherapy' },
          { id: 'wellness-spa-couples', label: "Couples' Spa" },
        ],
      },
      {
        id: 'wellness-yoga',
        label: 'Yoga',
        children: [
          { id: 'wellness-yoga-hatha', label: 'Hatha' },
          { id: 'wellness-yoga-vinyasa', label: 'Vinyasa' },
          { id: 'wellness-yoga-prenatal', label: 'Prenatal' },
          { id: 'wellness-yoga-kids', label: 'Kids Yoga' },
        ],
      },
      {
        id: 'wellness-meditation',
        label: 'Meditation',
        children: [
          { id: 'wellness-meditation-guided', label: 'Guided Sessions' },
          { id: 'wellness-meditation-sound', label: 'Sound Healing' },
          { id: 'wellness-meditation-mindfulness', label: 'Mindfulness' },
        ],
      },
      { id: 'wellness-ayurveda', label: 'Ayurveda', children: [
        { id: 'wellness-ayurveda-panchakarma', label: 'Panchakarma' },
        { id: 'wellness-ayurveda-herbal', label: 'Herbal Treatments' },
      ]},
      { id: 'wellness-nutrition', label: 'Nutrition & Diet', children: [
        { id: 'wellness-nutrition-consulting', label: 'Diet Consulting' },
        { id: 'wellness-nutrition-weight', label: 'Weight Management' },
      ]},
      { id: 'wellness-float', label: 'Float Therapy', children: [] },
    ],
  },
  {
    id: 'beauty',
    label: 'Beauty',
    children: [
      {
        id: 'beauty-hair',
        label: 'Hair',
        children: [
          { id: 'beauty-hair-salon', label: 'Salon' },
          { id: 'beauty-hair-color', label: 'Colouring & Highlights' },
          { id: 'beauty-hair-extensions', label: 'Extensions' },
          { id: 'beauty-hair-treatment', label: 'Treatments & Spa' },
          { id: 'beauty-hair-mens', label: "Men's Grooming" },
          { id: 'beauty-hair-barber', label: 'Barbershop' },
        ],
      },
      {
        id: 'beauty-skin',
        label: 'Skin Care',
        children: [
          { id: 'beauty-skin-facial', label: 'Facials' },
          { id: 'beauty-skin-acne', label: 'Acne Treatment' },
          { id: 'beauty-skin-antiaging', label: 'Anti-Ageing' },
          { id: 'beauty-skin-derma', label: 'Dermatology' },
        ],
      },
      {
        id: 'beauty-nails',
        label: 'Nails',
        children: [
          { id: 'beauty-nails-gel', label: 'Gel & Acrylics' },
          { id: 'beauty-nails-nail-art', label: 'Nail Art' },
          { id: 'beauty-nails-pedicure', label: 'Pedicure' },
        ],
      },
      { id: 'beauty-makeup', label: 'Makeup', children: [
        { id: 'beauty-makeup-bridal', label: 'Bridal Makeup' },
        { id: 'beauty-makeup-studio', label: 'Studio Makeup' },
        { id: 'beauty-makeup-lessons', label: 'Makeup Lessons' },
      ]},
      { id: 'beauty-waxing', label: 'Waxing & Threading', children: [] },
      { id: 'beauty-tattoo', label: 'Tattoo & Piercing', children: [
        { id: 'beauty-tattoo-fine', label: 'Fine Line' },
        { id: 'beauty-tattoo-traditional', label: 'Traditional' },
      ]},
    ],
  },
  {
    id: 'sports',
    label: 'Sports',
    children: [
      {
        id: 'sports-courts',
        label: 'Court Sports',
        children: [
          { id: 'sports-courts-badminton', label: 'Badminton' },
          { id: 'sports-courts-tennis', label: 'Tennis' },
          { id: 'sports-courts-squash', label: 'Squash' },
          { id: 'sports-courts-basketball', label: 'Basketball' },
          { id: 'sports-courts-volleyball', label: 'Volleyball' },
        ],
      },
      {
        id: 'sports-fitness',
        label: 'Fitness',
        children: [
          { id: 'sports-fitness-gym', label: 'Gym' },
          { id: 'sports-fitness-crossfit', label: 'CrossFit' },
          { id: 'sports-fitness-pilates', label: 'Pilates' },
          { id: 'sports-fitness-zumba', label: 'Zumba & Dance' },
          { id: 'sports-fitness-functional', label: 'Functional Training' },
        ],
      },
      {
        id: 'sports-martial',
        label: 'Martial Arts',
        children: [
          { id: 'sports-martial-mma', label: 'MMA' },
          { id: 'sports-martial-boxing', label: 'Boxing' },
          { id: 'sports-martial-karate', label: 'Karate' },
          { id: 'sports-martial-judo', label: 'Judo' },
          { id: 'sports-martial-taekwondo', label: 'Taekwondo' },
        ],
      },
      { id: 'sports-swimming', label: 'Swimming', children: [
        { id: 'sports-swimming-coaching', label: 'Coaching' },
        { id: 'sports-swimming-lap', label: 'Lap Pool' },
      ]},
      { id: 'sports-cricket', label: 'Cricket', children: [
        { id: 'sports-cricket-academy', label: 'Academy' },
        { id: 'sports-cricket-nets', label: 'Practice Nets' },
      ]},
      { id: 'sports-football', label: 'Football / Futsal', children: [] },
      { id: 'sports-cycling', label: 'Cycling', children: [] },
      { id: 'sports-shooting', label: 'Shooting & Archery', children: [] },
    ],
  },
  {
    id: 'retail',
    label: 'Retail',
    children: [
      {
        id: 'retail-electronics',
        label: 'Electronics',
        children: [
          { id: 'retail-electronics-phones', label: 'Phones & Accessories' },
          { id: 'retail-electronics-gadgets', label: 'Gadgets' },
          { id: 'retail-electronics-repairs', label: 'Repairs' },
        ],
      },
      {
        id: 'retail-homedecor',
        label: 'Home & Decor',
        children: [
          { id: 'retail-homedecor-furniture', label: 'Furniture' },
          { id: 'retail-homedecor-art', label: 'Art & Prints' },
          { id: 'retail-homedecor-plants', label: 'Plants & Pots' },
          { id: 'retail-homedecor-lighting', label: 'Lighting' },
        ],
      },
      { id: 'retail-gifts', label: 'Gifts & Souvenirs', children: [
        { id: 'retail-gifts-personalised', label: 'Personalised Gifts' },
        { id: 'retail-gifts-corporate', label: 'Corporate Gifts' },
      ]},
      { id: 'retail-books', label: 'Books & Stationery', children: [
        { id: 'retail-books-secondhand', label: 'Second-Hand Books' },
        { id: 'retail-books-art', label: 'Art Supplies' },
      ]},
      { id: 'retail-grocery', label: 'Specialty Grocery', children: [
        { id: 'retail-grocery-organic', label: 'Organic & Natural' },
        { id: 'retail-grocery-imported', label: 'Imported Foods' },
      ]},
      { id: 'retail-pets', label: 'Pet Store', children: [
        { id: 'retail-pets-supplies', label: 'Pet Supplies' },
        { id: 'retail-pets-grooming', label: 'Pet Grooming' },
      ]},
      { id: 'retail-toys', label: 'Toys & Games', children: [] },
      { id: 'retail-sports-gear', label: 'Sports Gear', children: [] },
    ],
  },
  {
    id: 'entertainment',
    label: 'Entertainment',
    children: [
      {
        id: 'entertainment-events',
        label: 'Events & Venues',
        children: [
          { id: 'entertainment-events-corporate', label: 'Corporate Events' },
          { id: 'entertainment-events-birthday', label: 'Birthday Parties' },
          { id: 'entertainment-events-wedding', label: 'Weddings' },
          { id: 'entertainment-events-concerts', label: 'Concerts' },
        ],
      },
      {
        id: 'entertainment-gaming',
        label: 'Gaming',
        children: [
          { id: 'entertainment-gaming-arcade', label: 'Arcade' },
          { id: 'entertainment-gaming-vr', label: 'VR Gaming' },
          { id: 'entertainment-gaming-esports', label: 'Esports Café' },
          { id: 'entertainment-gaming-boardgames', label: 'Board Game Café' },
        ],
      },
      {
        id: 'entertainment-arts',
        label: 'Arts & Culture',
        children: [
          { id: 'entertainment-arts-gallery', label: 'Art Gallery' },
          { id: 'entertainment-arts-pottery', label: 'Pottery & Ceramics' },
          { id: 'entertainment-arts-painting', label: 'Painting Classes' },
          { id: 'entertainment-arts-theatre', label: 'Theatre' },
        ],
      },
      { id: 'entertainment-music', label: 'Live Music', children: [
        { id: 'entertainment-music-jazz', label: 'Jazz' },
        { id: 'entertainment-music-band', label: 'Live Band' },
        { id: 'entertainment-music-dj', label: 'DJ Night' },
      ]},
      { id: 'entertainment-escape', label: 'Escape Room', children: [] },
      { id: 'entertainment-comedy', label: 'Comedy Club', children: [] },
      { id: 'entertainment-photobooth', label: 'Photo Booth / Studio', children: [] },
    ],
  },
]

// ── Lookup helpers ────────────────────────────────────────────────────────────

export function findNode(id: string, nodes = NICHE_TAXONOMY): NicheNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    if (node.children) {
      const found = findNode(id, node.children)
      if (found) return found
    }
  }
  return null
}

export function getAncestors(id: string, nodes = NICHE_TAXONOMY, path: NicheNode[] = []): NicheNode[] {
  for (const node of nodes) {
    const next = [...path, node]
    if (node.id === id) return next
    if (node.children) {
      const found = getAncestors(id, node.children, next)
      if (found.length) return found
    }
  }
  return []
}

export function getIndustryForNode(id: string): NicheNode | null {
  for (const industry of NICHE_TAXONOMY) {
    if (industry.id === id) return industry
    if (findNode(id, industry.children ?? [])) return industry
  }
  return null
}
