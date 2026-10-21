"""Builders for Lighthouse payloads shared across tests"""


def performance_audits():
    return {
        "first-contentful-paint": {"numericValue": 100},
        "largest-contentful-paint": {"numericValue": 200},
        "speed-index": {"numericValue": 300},
        "total-blocking-time": {"numericValue": 10},
        "mainthread-work-breakdown": {
            "numericValue": 5,
            "details": {"items": [{"group": "script", "duration": 1.0}]},
        },
        "diagnostics": {
            "details": {"items": [{"numRequests": 1, "numTasks": 2, "totalByteWeight": 3}]},
        },
        "network-requests": {
            "details": {"items": [{"statusCode": 200, "transferSize": 100}]},
        },
        "resource-summary": {
            "details": {
                "items": [
                    {"resourceType": "total", "transferSize": 1000},
                    {"resourceType": "image", "transferSize": 200},
                    {"resourceType": "script", "transferSize": 300},
                    {"resourceType": "stylesheet", "transferSize": 100},
                    {"resourceType": "document", "transferSize": 50},
                    {"resourceType": "third-party", "transferSize": 400},
                ]
            }
        },
        "network-server-latency": {
            "numericValue": 50,
            "details": {"items": [{"origin": "https://example.com", "serverResponseTime": 50}]},
        },
    }


def lighthouse_payload(categories="performance,seo", url="https://example.com", audits=None, cats=None):
    """A full lighthouse result with one successful url, the same data for mobile and desktop"""
    audits = performance_audits() if audits is None else audits
    cats = {} if cats is None else cats
    return {
        "meta": {"categories": categories},
        "lighthouse_data": {
            url: {
                "status": "success",
                "mobile": {"audits": audits, "categories": cats},
                "desktop": {"audits": audits, "categories": cats},
            }
        },
    }
