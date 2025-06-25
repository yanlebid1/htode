# Bot Naming Scheme - Ukrainian Flowers 🌸

This document defines the naming scheme for the multi-bot architecture using beautiful flower names.

## Naming Pattern

- **Dispatcher Bot**: `@HtodeNavigatorBot` (The Navigator - guides users to their flower)
- **Pool Bots**: `@hto_de_[flower]_bot`

## Actual Bot Names (20 Flower Bots)

Based on your created bots from [t.me/hto_de_daisy_bot](https://t.me/hto_de_daisy_bot), [t.me/hto_de_tulip_bot](https://t.me/hto_de_tulip_bot), and [t.me/hto_de_lavender_bot](https://t.me/hto_de_lavender_bot):

### Pool Bots (20 Flowers)

1. **@hto_de_orchid_bot** - 🌺 Орхідея (Orchid - Elegance)
2. **@hto_de_tulip_bot** - 🌷 Тюльпан (Tulip - Perfect Love)
3. **@hto_de_daisy_bot** - 🌼 Маргаритка (Daisy - Innocence)
4. **@hto_de_lavender_bot** - 💜 Лаванда (Lavender - Serenity)
5. **@hto_de_jasmine_bot** - 🤍 Жасмин (Jasmine - Grace)
6. **@hto_de_sunflower_bot** - 🌻 Соняшник (Sunflower - Loyalty)
7. **@hto_de_lotus_bot** - 🪷 Лотос (Lotus - Rebirth)
8. **@hto_de_peony_bot** - 🌸 Півонія (Peony - Honor)
9. **@hto_de_violet_bot** - 💙 Фіалка (Violet - Modesty)
10. **@hto_de_azalea_bot** - 🌺 Азалія (Azalea - Temperance)
11. **@hto_de_clover_bot** - 🍀 Конюшина (Clover - Good Luck)
12. **@hto_de_marigold_bot** - 🧡 Нагідки (Marigold - Passion)
13. **@hto_de_bluebell_bot** - 💙 Дзвіночок (Bluebell - Gratitude)
14. **@hto_de_gardenia_bot** - 🤍 Гарденія (Gardenia - Purity)
15. **@hto_de_aster_bot** - 💜 Астра (Aster - Patience)
16. **@hto_de_hibiscus_bot** - 🌺 Гібіскус (Hibiscus - Delicate Beauty)
17. **@hto_de_freesia_bot** - 💛 Фрезія (Freesia - Friendship)
18. **@hto_de_verbena_bot** - 💜 Вербена (Verbena - Healing)
19. **@hto_de_hyacinth_bot** - 💙 Гіацинт (Hyacinth - Sport)
20. **@hto_de_fuchsia_bot** - 💖 Фуксія (Fuchsia - Amiability)

## User Experience Messages

When users are assigned to a bot, they'll see friendly messages like:

- "Ваш персональний помічник - квітка Орхідея 🌺"
- "Вас обслуговує квітка Тюльпан 🌷"  
- "Ваш провідник у світі нерухомості - квітка Лаванда 💜"

## Bot Descriptions (for BotFather)

### Pool Bots Example
**Name**: HTO.DE Orchid
**Description**: 🌺 Квітка Орхідея - ваш персональний помічник з пошуку нерухомості
**About**: Бот-помічник HTO.DE. Надсилає персоналізовані пропозиції нерухомості.

## Why Flowers Are Perfect

1. **Beautiful & Memorable**: "I'm with Orchid" sounds elegant and personal
2. **Universal Appeal**: Flowers are loved across all cultures
3. **Home Connection**: Flowers represent beauty, growth, and making a house a home
4. **Positive Associations**: Each flower has positive symbolic meanings
5. **Scalable**: Thousands of flower species exist for future expansion
6. **Gender Neutral**: Appeals to all demographics

## Technical Benefits

- **User Retention**: People remember "Orchid bot" better than "bot_1"
- **Brand Consistency**: Aligns with home/beauty theme of real estate
- **Support Efficiency**: "I'm having issues with Tulip" is clearer than "bot_2"
- **Marketing Friendly**: "Our beautiful flower bots" sounds professional

## Environment Variable Mapping

```env
# Dispatcher
TELEGRAM_DISPATCHER_TOKEN=your_token_here
TELEGRAM_DISPATCHER_USERNAME=@HtodeNavigatorBot

# Pool Bots
BOT_POOL_1_TOKEN=your_token_here
BOT_POOL_1_USERNAME=@hto_de_orchid_bot
BOT_POOL_1_INTERNAL_NAME=orchid

BOT_POOL_2_TOKEN=your_token_here
BOT_POOL_2_USERNAME=@hto_de_tulip_bot
BOT_POOL_2_INTERNAL_NAME=tulip

# ... and so on
```

## Future Expansion

If we need more than 20 bots, we can use:
- Southern hemisphere constellations
- Star names (Sirius, Vega, Polaris)
- Planetary names
- Ukrainian astronomical observatories 