'use client'

import React, { ReactNode, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

interface ProtectedRouteProps {
  children: ReactNode
  requiredPermission?: string
  fallback?: ReactNode
}

export function ProtectedRoute({
  children,
  requiredPermission,
  fallback
}: ProtectedRouteProps) {
  const DEBUG = process.env.NODE_ENV !== 'production'
  const { isAuthenticated, authResolved, hasUIAccess, canAccessPage } = useAuth()
  const router = useRouter()
  const [redirecting, setRedirecting] = useState(false)

  useEffect(() => {
    if (!authResolved || redirecting) return

    if (!isAuthenticated) {
      setRedirecting(true)
      if (DEBUG) console.log('ProtectedRoute - Redirecting to login (no auth)')
      router.push('/login')
      return
    }
    if (isAuthenticated && !hasUIAccess) {
      setRedirecting(true)
      if (DEBUG) console.log('ProtectedRoute - Redirecting to 403 (no UI access)')
      router.push('/403')
      return
    }
  }, [authResolved, isAuthenticated, hasUIAccess, router, redirecting])

  if (!authResolved || redirecting) {
    return fallback || (
      <div className="min-h-screen bg-gray-50 dark:bg-dark-bg flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 shadow-lg rounded-lg p-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              Redirecting...
            </h2>
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return fallback || (
      <div className="min-h-screen bg-gray-50 dark:bg-dark-bg flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 shadow-lg rounded-lg p-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              Authentication Required
            </h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              Please log in to access this page.
            </p>
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  if (isAuthenticated && !hasUIAccess) {
    return fallback || (
      <div className="min-h-screen bg-gray-50 dark:bg-dark-bg flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 shadow-lg rounded-lg p-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              UI Access Denied
            </h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              You do not have permission to access the web interface.
            </p>
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  if (requiredPermission && !canAccessPage(requiredPermission)) {
    const permissionMessages: Record<string, string> = {
      'manage_users': 'User Management',
      'manage_apis': 'API Management',
      'manage_endpoints': 'Endpoint Management',
      'manage_groups': 'Group Management',
      'manage_roles': 'Role Management',
      'manage_routings': 'Routing Management',
      'manage_gateway': 'Gateway Management',
      'manage_subscriptions': 'Subscription Management',
      'manage_security': 'Security Management',
      'manage_credits': 'Credit Management',
      'manage_tiers': 'Tier Management',
      'manage_auth': 'Auth Administration',
      'view_logs': 'System Logs',
      'view_analytics': 'Analytics',
      'view_builder_tables': 'Tables'
    }

    const permissionName = permissionMessages[requiredPermission] || requiredPermission

    return fallback || (
      <div className="min-h-screen bg-signal-warm flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white border-[3px] border-signal-ink shadow-[6px_6px_0px_0px_rgba(25,32,28,1)]">
          <div className="px-5 py-3.5 border-b-[3px] border-signal-ink bg-signal-terra text-white flex items-center justify-between">
            <span className="font-mono text-xs font-bold uppercase tracking-wider">Access Policy Violation</span>
            <span className="font-mono text-xs font-extrabold">[ 403 ]</span>
          </div>
          <div className="p-6 text-center space-y-4">
            <h2 className="text-2xl font-extrabold text-signal-ink tracking-tight">Access Denied</h2>
            <p className="text-sm text-signal-mist">
              Your account does not possess the required administrative privilege to view this resource.
            </p>
            <div className="p-2.5 bg-signal-warm border-2 border-signal-ink font-mono text-xs text-signal-ink">
              Required: <span className="font-bold underline">{permissionName}</span>
            </div>
            <div className="flex gap-3 justify-center pt-2">
              <button onClick={() => router.back()} className="signal-button btn-secondary text-xs">
                Go Back
              </button>
              <button onClick={() => router.push('/dashboard')} className="signal-button signal-button--primary text-xs">
                Dashboard
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
