#!/bin/bash
# Start Flower Bot Garden - Convenience Script

set -e

echo "🌸 Starting HTO.DE Flower Bot Garden..."

# Function to start specific number of flower bots
start_flowers() {
    local count=${1:-5}  # Default to 5 bots
    
    echo "🌱 Starting dispatcher bot..."
    docker-compose -f docker-compose.multibot-full.yml up -d dispatcher_bot
    
    echo "🌸 Starting $count flower bots..."
    
    services=()
    worker_services=()
    
    if [ $count -ge 1 ]; then
        services+=(pool_bot_orchid)
        worker_services+=(pool_bot_worker_orchid)
        echo "  🌺 Adding Orchid bot..."
    fi

    if [ $count -ge 2 ]; then
        services+=(pool_bot_tulip)
        worker_services+=(pool_bot_worker_tulip)
        echo "  🌷 Adding Tulip bot..."
    fi

    if [ $count -ge 3 ]; then
        services+=(pool_bot_daisy)
        worker_services+=(pool_bot_worker_daisy)
        echo "  🌼 Adding Daisy bot..."
    fi

    if [ $count -ge 4 ]; then
        services+=(pool_bot_lavender)
        worker_services+=(pool_bot_worker_lavender)
        echo "  💜 Adding Lavender bot..."
    fi

    if [ $count -ge 5 ]; then
        services+=(pool_bot_jasmine)
        worker_services+=(pool_bot_worker_jasmine)
        echo "  🤍 Adding Jasmine bot..."
    fi

    if [ $count -ge 6 ]; then
        services+=(pool_bot_sunflower)
        worker_services+=(pool_bot_worker_sunflower)
        echo "  🌻 Adding Sunflower bot..."
    fi

    if [ $count -ge 7 ]; then
        services+=(pool_bot_lotus)
        worker_services+=(pool_bot_worker_lotus)
        echo "  🪷 Adding Lotus bot..."
    fi

    if [ $count -ge 8 ]; then
        services+=(pool_bot_peony)
        worker_services+=(pool_bot_worker_peony)
        echo "  🌸 Adding Peony bot..."
    fi

    if [ $count -ge 9 ]; then
        services+=(pool_bot_violet)
        worker_services+=(pool_bot_worker_violet)
        echo "  💙 Adding Violet bot..."
    fi

    if [ $count -ge 10 ]; then
        services+=(pool_bot_azalea)
        worker_services+=(pool_bot_worker_azalea)
        echo "  🌺 Adding Azalea bot..."
    fi

    if [ $count -ge 11 ]; then
        services+=(pool_bot_clover)
        worker_services+=(pool_bot_worker_clover)
        echo "  🍀 Adding Clover bot..."
    fi

    if [ $count -ge 12 ]; then
        services+=(pool_bot_marigold)
        worker_services+=(pool_bot_worker_marigold)
        echo "  🧡 Adding Marigold bot..."
    fi

    if [ $count -ge 13 ]; then
        services+=(pool_bot_bluebell)
        worker_services+=(pool_bot_worker_bluebell)
        echo "  💙 Adding Bluebell bot..."
    fi

    if [ $count -ge 14 ]; then
        services+=(pool_bot_gardenia)
        worker_services+=(pool_bot_worker_gardenia)
        echo "  🤍 Adding Gardenia bot..."
    fi

    if [ $count -ge 15 ]; then
        services+=(pool_bot_aster)
        worker_services+=(pool_bot_worker_aster)
        echo "  💜 Adding Aster bot..."
    fi

    if [ $count -ge 16 ]; then
        services+=(pool_bot_hibiscus)
        worker_services+=(pool_bot_worker_hibiscus)
        echo "  🌺 Adding Hibiscus bot..."
    fi

    if [ $count -ge 17 ]; then
        services+=(pool_bot_freesia)
        worker_services+=(pool_bot_worker_freesia)
        echo "  💛 Adding Freesia bot..."
    fi

    if [ $count -ge 18 ]; then
        services+=(pool_bot_verbena)
        worker_services+=(pool_bot_worker_verbena)
        echo "  💜 Adding Verbena bot..."
    fi

    if [ $count -ge 19 ]; then
        services+=(pool_bot_hyacinth)
        worker_services+=(pool_bot_worker_hyacinth)
        echo "  💙 Adding Hyacinth bot..."
    fi

    if [ $count -ge 20 ]; then
        services+=(pool_bot_fuchsia)
        worker_services+=(pool_bot_worker_fuchsia)
        echo "  💖 Adding Fuchsia bot..."
    fi


    # Start bot services
    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.multibot-full.yml up -d "${services[@]}"
    fi
    
    # Start worker services
    if [ ${#worker_services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.multibot-full.yml up -d "${worker_services[@]}"
    fi
    
    echo "✅ Started $count flower bots successfully!"
    echo "🔍 Monitor with: python scripts/monitor_multibot_system.py"
}

# Parse command line arguments
case "${1:-5}" in
    "test"|"2")
        echo "🧪 Test mode - starting 2 flower bots (Orchid + Tulip)"
        start_flowers 2
        ;;
    "small"|"5")
        echo "🌿 Small garden - starting 5 flower bots"
        start_flowers 5
        ;;
    "medium"|"10")
        echo "🌻 Medium garden - starting 10 flower bots"
        start_flowers 10
        ;;
    "full"|"20")
        echo "🌺 Full garden - starting all 20 flower bots!"
        start_flowers 20
        ;;
    *)
        if [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 20 ]; then
            echo "🌸 Custom garden - starting $1 flower bots"
            start_flowers $1
        else
            echo "Usage: $0 [test|small|medium|full|NUMBER]"
            echo ""
            echo "Options:"
            echo "  test    - Start 2 bots (Orchid + Tulip)"
            echo "  small   - Start 5 bots"
            echo "  medium  - Start 10 bots"
            echo "  full    - Start all 20 bots"
            echo "  NUMBER  - Start specific number (1-20)"
            exit 1
        fi
        ;;
esac
