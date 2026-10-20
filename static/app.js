"use strict";

function describeGeolocationError(error) {
    if (error.code === error.PERMISSION_DENIED) {
        return "Location permission was denied. You can enable it in your browser settings and try again.";
    }
    if (error.code === error.POSITION_UNAVAILABLE) {
        return "Your location is currently unavailable. Check your device settings and try again.";
    }
    if (error.code === error.TIMEOUT) {
        return "The location request timed out. Please try again.";
    }
    return "Your location could not be obtained. Please try again.";
}

document.querySelectorAll("[data-location]").forEach(function (button) {
    button.addEventListener("click", function () {
        const result = document.querySelector("[data-location-result]");
        result.textContent = "";
        if (!navigator.geolocation) {
            result.textContent = "Geolocation is not supported by this browser.";
            return;
        }

        result.textContent = "Requesting location permission…";
        navigator.geolocation.getCurrentPosition(
            function (position) {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                result.replaceChildren();

                const coordinates = document.createElement("p");
                coordinates.textContent =
                    "Latitude: " + latitude.toFixed(5) +
                    " · Longitude: " + longitude.toFixed(5);
                const mapLink = document.createElement("a");
                mapLink.href =
                    "https://www.google.com/maps?q=" +
                    encodeURIComponent(latitude + "," + longitude);
                mapLink.target = "_blank";
                mapLink.rel = "noopener noreferrer";
                mapLink.textContent = "Open coordinates in a map";
                result.append(coordinates, mapLink);
            },
            function (error) {
                result.textContent = describeGeolocationError(error);
            },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }
        );
    });
});

document.querySelectorAll("[data-sos]").forEach(function (button) {
    button.addEventListener("click", function () {
        if (!window.confirm(
            "Activate the demo SOS status? This will not contact emergency services or send an alert."
        )) {
            return;
        }
        const shareLocation = window.confirm(
            "Would you like to request your location for display on this page? It will not be sent or stored."
        );
        const status = document.querySelector("[data-sos-result]");
        if (!shareLocation) {
            status.textContent =
                "Demo SOS status activated. No alert was sent or delivered.";
            return;
        }
        if (!navigator.geolocation) {
            status.textContent =
                "Demo SOS status activated. Location is unavailable in this browser; no alert was sent.";
            return;
        }
        status.textContent = "Demo SOS status activated. Requesting optional location permission…";
        navigator.geolocation.getCurrentPosition(
            function (position) {
                status.textContent =
                    "Demo SOS status activated for this page. Coordinates: " +
                    position.coords.latitude.toFixed(5) + ", " +
                    position.coords.longitude.toFixed(5) +
                    ". Nothing was sent or delivered.";
            },
            function (error) {
                status.textContent =
                    "Demo SOS status activated. " + describeGeolocationError(error) +
                    " No alert was sent or delivered.";
            },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }
        );
    });
});
