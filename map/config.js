/**
 * CDV Map Configuration
 * API keys and settings for the parcel intelligence map
 */

const CDV_CONFIG = {
    // Mapbox
    mapbox: {
        accessToken: 'pk.eyJ1IjoiamVhbnBhdWwwOSIsImEiOiJjbWpqMWdmNmMxdjVvM2VxMzM5Nm92bmg3In0.2UPggL-HJqybJ3gk0smJAw',
        defaultCenter: [-80.1918, 25.7617], // Miami
        defaultZoom: 12,
        styles: {
            dark: 'mapbox://styles/mapbox/dark-v11',
            satellite: 'mapbox://styles/mapbox/satellite-streets-v12',
            streets: 'mapbox://styles/mapbox/streets-v12'
        }
    },
    
    // PropertyReach API
    propertyReach: {
        apiKey: 'test_T9ktTlVrUgZuetmMperHBKm1i3P4jeSFamr',
        baseUrl: 'https://api.propertyreach.com/v1'
        endpoints: {
            parcels: '/parcels',
            parcelDetails: '/parcels/{id}',
            search: '/search'
        }
    },
    
    // Miami-Dade EnerGov (existing scraper)
    energov: {
        baseUrl: 'https://energov.miamidade.gov/EnerGov_Prod/SelfService',
        apiBase: '/api/energov'
    },
    
    // Map bounds for Miami-Dade County
    bounds: {
        miami: {
            sw: [-80.87, 25.14],  // Southwest
            ne: [-80.03, 25.97]   // Northeast
        }
    },
    
    // Parcel layer styling
    parcelStyles: {
        default: {
            fillColor: '#00d4aa',
            fillOpacity: 0.15,
            lineColor: '#00d4aa',
            lineWidth: 2
        },
        selected: {
            fillColor: '#4ecdc4',
            fillOpacity: 0.35,
            lineColor: '#4ecdc4',
            lineWidth: 3
        },
        hasPermit: {
            fillColor: '#ff6b35',
            fillOpacity: 0.25,
            lineColor: '#ff6b35',
            lineWidth: 2
        }
    }
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CDV_CONFIG;
}

