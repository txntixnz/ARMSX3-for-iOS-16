// SPDX-License-Identifier: GPL-2.0-only
#include "GraphicsDevice.h"
#include <vulkan/vulkan.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>

namespace ios_graphics
{
namespace
{
constexpr std::uint32_t width = 32, height = 32, bytes = width * height * 4;
std::mutex device_mutex;
bool unavailable_until_restart = false;
void checked(VkResult result, const char* operation)
{
    if (result != VK_SUCCESS) throw std::runtime_error(std::string(operation) + ": VkResult=" + std::to_string(result));
}
template<class T, class F> std::vector<T> enumerate(F fetch, const char* operation)
{
    for (unsigned attempt = 0; attempt < 4; ++attempt)
    {
        std::uint32_t count = 0;
        checked(fetch(&count, static_cast<T*>(nullptr)), operation);
        if (count > 65536) throw std::runtime_error("Graphics enumeration exceeds bound");
        std::vector<T> values(count);
        if (!count) return values;
        const auto result = fetch(&count, values.data());
        if (result == VK_INCOMPLETE) continue;
        checked(result, operation);
        values.resize(count);
        return values;
    }
    throw std::runtime_error("Graphics enumeration kept changing");
}
bool extension(const std::vector<VkExtensionProperties>& values, const char* name)
{
    return std::any_of(values.begin(), values.end(), [name](const auto& value) { return std::strcmp(value.extensionName, name) == 0; });
}
struct Resources
{
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkImage image = VK_NULL_HANDLE;
    VkDeviceMemory image_memory = VK_NULL_HANDLE, buffer_memory = VK_NULL_HANDLE;
    VkBuffer buffer = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    void* mapped = nullptr;
    bool in_flight = false;
    ~Resources()
    {
        if (mapped) vkUnmapMemory(device, buffer_memory);
        if (fence) vkDestroyFence(device, fence, nullptr);
        if (pool) vkDestroyCommandPool(device, pool, nullptr);
        if (buffer) vkDestroyBuffer(device, buffer, nullptr);
        if (buffer_memory) vkFreeMemory(device, buffer_memory, nullptr);
        if (image) vkDestroyImage(device, image, nullptr);
        if (image_memory) vkFreeMemory(device, image_memory, nullptr);
        if (device) vkDestroyDevice(device, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
    }
};
std::uint32_t memory_type(const VkPhysicalDeviceMemoryProperties& properties, std::uint32_t bits, VkMemoryPropertyFlags required, VkMemoryPropertyFlags preferred)
{
    for (auto desired : {required | preferred, required})
        for (std::uint32_t i = 0; i < properties.memoryTypeCount; ++i)
            if ((bits & (1u << i)) && (properties.memoryTypes[i].propertyFlags & desired) == desired) return i;
    throw std::runtime_error("No compatible graphics memory type");
}
}

Result check_device(void (*log)(const char*))
{
    std::unique_lock lock(device_mutex, std::try_to_lock);
    if (!lock.owns_lock()) return {-1, "Graphics check is already active"};
    if (unavailable_until_restart) return {-2, "Previous GPU work did not finish; reopen the app"};
    auto resource = std::make_unique<Resources>();
    auto& r = *resource;
    auto emit = [log](const std::string& text) { if (log) log(text.c_str()); };
    try
    {
        const auto instance_extensions = enumerate<VkExtensionProperties>([](auto* count, auto* data) { return vkEnumerateInstanceExtensionProperties(nullptr, count, data); }, "Enumerate instance extensions");
        std::vector<const char*> enabled;
        VkInstanceCreateFlags flags = 0;
        // The Vulkan loader supplies portability enumeration. Directly linked
        // MoltenVK enumerates its devices without advertising that extension.
        // Enable the extension/flag pair only when it is actually advertised.
        emit("GRAPHICS instance extensions=" + std::to_string(instance_extensions.size()) +
            " portability enumeration=" + (extension(instance_extensions, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME) ? "advertised" : "not advertised; flags=0"));
        if (extension(instance_extensions, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME))
        {
            enabled.push_back(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME);
            flags |= VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
        }
        VkApplicationInfo app{};
        app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.pApplicationName = "ARMSX3 graphics check";
        app.apiVersion = VK_API_VERSION_1_1;
        VkInstanceCreateInfo instance{};
        instance.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        instance.flags = flags;
        instance.pApplicationInfo = &app;
        instance.enabledExtensionCount = static_cast<std::uint32_t>(enabled.size());
        instance.ppEnabledExtensionNames = enabled.data();
        checked(vkCreateInstance(&instance, nullptr, &r.instance), "Create Vulkan instance");
        const auto physical_devices = enumerate<VkPhysicalDevice>([&](auto* count, auto* data) { return vkEnumeratePhysicalDevices(r.instance, count, data); }, "Enumerate physical devices");
        VkPhysicalDevice physical = VK_NULL_HANDLE;
        std::uint32_t family = 0;
        for (auto candidate : physical_devices)
        {
            std::uint32_t count = 0;
            vkGetPhysicalDeviceQueueFamilyProperties(candidate, &count, nullptr);
            if (count > 65536) throw std::runtime_error("Graphics queue family count exceeds bound");
            std::vector<VkQueueFamilyProperties> queues(count);
            vkGetPhysicalDeviceQueueFamilyProperties(candidate, &count, queues.data());
            for (std::uint32_t i = 0; i < count; ++i)
                if (queues[i].queueCount && (queues[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { physical = candidate; family = i; break; }
            if (physical) break;
        }
        if (!physical) throw std::runtime_error("No Vulkan graphics device/queue is available");
        VkPhysicalDeviceProperties properties{};
        vkGetPhysicalDeviceProperties(physical, &properties);
        emit("GRAPHICS device=" + std::string(properties.deviceName) + " API=" + std::to_string(VK_VERSION_MAJOR(properties.apiVersion)) + "." + std::to_string(VK_VERSION_MINOR(properties.apiVersion)) + " driver=" + std::to_string(properties.driverVersion));
        VkPhysicalDeviceFeatures features{};
        vkGetPhysicalDeviceFeatures(physical, &features);
        emit("GRAPHICS capabilities: maxTexture2D=" + std::to_string(properties.limits.maxImageDimension2D) + " maxStorageBuffer=" + std::to_string(properties.limits.maxStorageBufferRange) + " geometry=" + std::to_string(features.geometryShader) + " tessellation=" + std::to_string(features.tessellationShader) + " fragmentStores=" + std::to_string(features.fragmentStoresAndAtomics));
        const auto device_extensions = enumerate<VkExtensionProperties>([&](auto* count, auto* data) { return vkEnumerateDeviceExtensionProperties(physical, nullptr, count, data); }, "Enumerate device extensions");
        std::vector<const char*> device_enabled;
        if (extension(device_extensions, "VK_KHR_portability_subset")) device_enabled.push_back("VK_KHR_portability_subset");
        const float priority = 1.f;
        VkDeviceQueueCreateInfo queue_info{};
        queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_info.queueFamilyIndex = family;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        VkDeviceCreateInfo device_info{};
        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        device_info.enabledExtensionCount = static_cast<std::uint32_t>(device_enabled.size());
        device_info.ppEnabledExtensionNames = device_enabled.data();
        checked(vkCreateDevice(physical, &device_info, nullptr, &r.device), "Create graphics device");
        VkQueue queue = VK_NULL_HANDLE;
        vkGetDeviceQueue(r.device, family, 0, &queue);
        VkPhysicalDeviceMemoryProperties memory{};
        vkGetPhysicalDeviceMemoryProperties(physical, &memory);
        VkFormatProperties format{};
        vkGetPhysicalDeviceFormatProperties(physical, VK_FORMAT_R8G8B8A8_UNORM, &format);
        if ((format.optimalTilingFeatures & (VK_FORMAT_FEATURE_TRANSFER_SRC_BIT | VK_FORMAT_FEATURE_TRANSFER_DST_BIT)) != (VK_FORMAT_FEATURE_TRANSFER_SRC_BIT | VK_FORMAT_FEATURE_TRANSFER_DST_BIT)) throw std::runtime_error("RGBA8 transfer format is unsupported");
        VkImageCreateInfo image{};
        image.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        image.imageType = VK_IMAGE_TYPE_2D;
        image.format = VK_FORMAT_R8G8B8A8_UNORM;
        image.extent = {width, height, 1};
        image.mipLevels = image.arrayLayers = 1;
        image.samples = VK_SAMPLE_COUNT_1_BIT;
        image.tiling = VK_IMAGE_TILING_OPTIMAL;
        image.usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
        image.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        checked(vkCreateImage(r.device, &image, nullptr, &r.image), "Create RGBA8 image");
        VkMemoryRequirements requirements{};
        vkGetImageMemoryRequirements(r.device, r.image, &requirements);
        VkMemoryAllocateInfo allocation{};
        allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memory_type(memory, requirements.memoryTypeBits, 0, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        checked(vkAllocateMemory(r.device, &allocation, nullptr, &r.image_memory), "Allocate image memory");
        checked(vkBindImageMemory(r.device, r.image, r.image_memory, 0), "Bind image memory");
        VkBufferCreateInfo buffer{};
        buffer.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        buffer.size = bytes;
        buffer.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
        buffer.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        checked(vkCreateBuffer(r.device, &buffer, nullptr, &r.buffer), "Create readback buffer");
        vkGetBufferMemoryRequirements(r.device, r.buffer, &requirements);
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memory_type(memory, requirements.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT, VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        const bool coherent = memory.memoryTypes[allocation.memoryTypeIndex].propertyFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
        checked(vkAllocateMemory(r.device, &allocation, nullptr, &r.buffer_memory), "Allocate readback memory");
        checked(vkBindBufferMemory(r.device, r.buffer, r.buffer_memory, 0), "Bind readback buffer");
        VkCommandPoolCreateInfo pool{};
        pool.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pool.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool.queueFamilyIndex = family;
        checked(vkCreateCommandPool(r.device, &pool, nullptr, &r.pool), "Create command pool");
        VkCommandBufferAllocateInfo command_info{};
        command_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        command_info.commandPool = r.pool;
        command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        command_info.commandBufferCount = 1;
        VkCommandBuffer command = VK_NULL_HANDLE;
        checked(vkAllocateCommandBuffers(r.device, &command_info, &command), "Allocate command buffer");
        VkFenceCreateInfo fence{};
        fence.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        checked(vkCreateFence(r.device, &fence, nullptr, &r.fence), "Create GPU fence");
        for (unsigned pass = 0; pass < 2; ++pass)
        {
            if (pass) { checked(vkResetFences(r.device, 1, &r.fence), "Reset GPU fence"); checked(vkResetCommandBuffer(command, 0), "Reset command buffer"); }
            VkCommandBufferBeginInfo begin{};
            begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
            begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
            checked(vkBeginCommandBuffer(command, &begin), "Begin command buffer");
            VkImageMemoryBarrier barrier{};
            barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
            barrier.srcAccessMask = pass ? VK_ACCESS_TRANSFER_READ_BIT : 0;
            barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            barrier.oldLayout = pass ? VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : VK_IMAGE_LAYOUT_UNDEFINED;
            barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
            barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
            barrier.image = r.image;
            barrier.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
            vkCmdPipelineBarrier(command, pass ? VK_PIPELINE_STAGE_TRANSFER_BIT : VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
            VkClearColorValue color{};
            color.float32[pass ? 2 : 0] = color.float32[3] = 1.f;
            vkCmdClearColorImage(command, r.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &color, 1, &barrier.subresourceRange);
            barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            barrier.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
            barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
            barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
            VkBufferImageCopy copy{};
            copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            copy.imageExtent = {width, height, 1};
            vkCmdCopyImageToBuffer(command, r.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, r.buffer, 1, &copy);
            VkBufferMemoryBarrier host{};
            host.sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER;
            host.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            host.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
            host.srcQueueFamilyIndex = host.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
            host.buffer = r.buffer;
            host.size = VK_WHOLE_SIZE;
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 0, nullptr, 1, &host, 0, nullptr);
            checked(vkEndCommandBuffer(command), "End command buffer");
            VkSubmitInfo submit{};
            submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &command;
            // A submission error can leave ownership uncertain. Quarantine
            // conservatively unless device loss explicitly terminates its work.
            r.in_flight = true;
            const auto submitted = vkQueueSubmit(queue, 1, &submit, r.fence);
            if (submitted == VK_ERROR_DEVICE_LOST) r.in_flight = false;
            checked(submitted, "Submit graphics work");
            const auto waited = vkWaitForFences(r.device, 1, &r.fence, VK_TRUE, 5'000'000'000ull);
            if (waited == VK_SUCCESS || waited == VK_ERROR_DEVICE_LOST) r.in_flight = false;
            checked(waited, "Wait for graphics work");
            checked(vkMapMemory(r.device, r.buffer_memory, 0, VK_WHOLE_SIZE, 0, &r.mapped), "Map graphics readback");
            if (!coherent)
            {
                VkMappedMemoryRange range{};
                range.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE;
                range.memory = r.buffer_memory;
                range.size = VK_WHOLE_SIZE;
                checked(vkInvalidateMappedMemoryRanges(r.device, 1, &range), "Invalidate graphics readback");
            }
            const auto* data = static_cast<const std::uint8_t*>(r.mapped);
            const std::array<std::uint8_t, 4> expected = pass ? std::array<std::uint8_t, 4>{0, 0, 255, 255} : std::array<std::uint8_t, 4>{255, 0, 0, 255};
            for (unsigned pixel = 0; pixel < width * height; ++pixel)
                if (std::memcmp(data + pixel * 4, expected.data(), 4)) throw std::runtime_error("GPU readback pixels do not match the submitted clear");
            vkUnmapMemory(r.device, r.buffer_memory);
            r.mapped = nullptr;
            emit("GRAPHICS PASS offscreen RGBA8 clear/copy/fence/readback pass=" + std::to_string(pass + 1) + " pixels=" + std::to_string(width * height));
        }
        return {0, std::string("Graphics device passed: ") + properties.deviceName + ". Two offscreen GPU clears and exact readback passed. Native game rendering and presentation are next."};
    }
    catch (const std::exception& error)
    {
        if (r.in_flight)
        {
            // Destruction while queued work is unfinished would invalidate its
            // image/buffer/pool. Retain the complete owner until process exit.
            unavailable_until_restart = true;
            resource.release();
            return {-2, std::string(error.what()) + "; GPU resources retained. Reopen the app."};
        }
        return {-1, error.what()};
    }
}
}
